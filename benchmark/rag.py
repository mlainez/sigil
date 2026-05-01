#!/usr/bin/env python3
"""Tiny RAG layer over the Sigil training corpus.

Indexes the user -> assistant pairs from training_corpus.jsonl (which
build_corpus.py aggregates from examples/corpus/, examples/corpus_extensions/,
and tests/) so that the corpus_extender pipeline can fetch the K most
similar prior solutions and inline them as few-shot examples before asking
ollama to generate.

All embeddings are local via ollama's nomic-embed-text (768-dim). No cloud
calls. No vector DB — for ~2K entries, dot-product over a numpy matrix in
RAM is more than fast enough (sub-millisecond per query).

CLI:
    python rag.py build                                  # build / refresh index
    python rag.py build --corpus path/to/file.jsonl
    python rag.py query "sum of squares of evens" -k 5   # show top-K
    python rag.py stats                                  # index size + dim
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "benchmark" / "training_corpus.jsonl"
INDEX_PATH = REPO_ROOT / "benchmark" / "rag_index.json"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"


def embed(text: str, url: str = OLLAMA_URL, model: str = EMBED_MODEL,
          timeout: int = 30) -> list[float]:
    """One embedding call via ollama. Returns a 768-d float list (nomic).
    Returns [] on failure — caller decides whether that's fatal."""
    body = json.dumps({"model": model, "prompt": text}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/embeddings",
        data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("embedding") or []
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return []


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine(a: list[float], b: list[float],
           na: float | None = None, nb: float | None = None) -> float:
    if not a or not b:
        return 0.0
    na = na if na is not None else _norm(a)
    nb = nb if nb is not None else _norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _load_pairs(corpus_path: Path) -> list[dict]:
    pairs = []
    with corpus_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = d.get("messages", [])
            user = next((m["content"] for m in msgs if m.get("role") == "user"), "")
            asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")
            if user and asst:
                pairs.append({"desc": user, "code": asst})
    return pairs


def build_index(corpus_path: Path = CORPUS_PATH,
                out_path: Path = INDEX_PATH,
                url: str = OLLAMA_URL,
                model: str = EMBED_MODEL,
                progress_every: int = 50) -> dict:
    """Read training_corpus.jsonl, embed every user description, save to
    out_path. Embedding the description (not the code) — task queries are
    descriptions, so query/index modality matches.
    """
    pairs = _load_pairs(corpus_path)
    print(f"Loaded {len(pairs)} pairs from {corpus_path}")
    print(f"Embedding via ollama {model} @ {url}...")

    entries = []
    for i, p in enumerate(pairs, 1):
        v = embed(p["desc"], url=url, model=model)
        if not v:
            print(f"  WARN: empty embedding for entry {i} (skipping)")
            continue
        entries.append({"desc": p["desc"], "code": p["code"],
                        "embedding": v, "norm": _norm(v)})
        if i % progress_every == 0:
            print(f"  {i}/{len(pairs)}")

    dim = len(entries[0]["embedding"]) if entries else 0
    out = {
        "model": model,
        "dim": dim,
        "count": len(entries),
        "source": str(corpus_path),
        "entries": entries,
    }
    out_path.write_text(json.dumps(out))
    print(f"Wrote {len(entries)} entries (dim={dim}) -> {out_path}")
    return {"count": len(entries), "dim": dim, "path": str(out_path)}


def load_index(path: Path = INDEX_PATH) -> dict:
    return json.loads(path.read_text())


def query(text: str, k: int = 5,
          index_path: Path = INDEX_PATH,
          url: str = OLLAMA_URL,
          model: str = EMBED_MODEL,
          index: dict | None = None,
          min_score: float = 0.72,
          mmr_lambda: float = 1.0,
          mmr_pool: int = 30,
          top1_floor: float = 0.78) -> list[dict]:
    """Top-K nearest neighbors. Returns list of {score, desc, code}.
    Pass `index` to avoid re-loading from disk on every query.

    Args:
        min_score: drop hits with cosine < this threshold. Use ~0.65 to skip
            low-quality retrievals that mislead more than they help.
        mmr_lambda: 1.0 = pure top-K by similarity (default).
            < 1.0 = blend in maximal-marginal-relevance to diversify
            results: each subsequent pick maximizes
                lambda * sim(q, e) - (1-lambda) * max_{p in picked} sim(e, p).
            Try 0.7 to spread retrievals across different solution shapes.
        mmr_pool: when MMR is on, scan the top mmr_pool candidates first.
        top1_floor: if the best match is below this score, return [] entirely
            — empty RAG block lets the model fall through to the grammar
            header alone, which avoids being misled by weakly-related
            retrievals on out-of-corpus queries.
    """
    if index is None:
        index = load_index(index_path)
    qv = embed(text, url=url, model=model)
    if not qv:
        return []
    qn = _norm(qv)
    scored = []
    for e in index["entries"]:
        s = cosine(qv, e["embedding"], na=qn, nb=e.get("norm"))
        if s >= min_score:
            scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    # Adaptive cutoff: if even the best hit is weak, we're querying outside
    # what the corpus covers — better to send no examples than misleading ones.
    if scored and scored[0][0] < top1_floor:
        return []

    if mmr_lambda >= 1.0 or len(scored) <= k:
        picked = scored[:k]
    else:
        pool = scored[:max(k, mmr_pool)]
        picked: list[tuple[float, dict]] = []
        remaining = list(pool)
        while remaining and len(picked) < k:
            best_idx = 0
            best_score = -1e9
            for i, (sim_q, e) in enumerate(remaining):
                if not picked:
                    score = sim_q
                else:
                    max_sim_to_picked = max(
                        cosine(e["embedding"], p[1]["embedding"],
                               na=e.get("norm"), nb=p[1].get("norm"))
                        for p in picked
                    )
                    score = mmr_lambda * sim_q - (1 - mmr_lambda) * max_sim_to_picked
                if score > best_score:
                    best_score = score
                    best_idx = i
            picked.append(remaining.pop(best_idx))

    return [{"score": s, "desc": e["desc"], "code": e["code"]}
            for s, e in picked]


def format_examples(hits: list[dict], header: str = "Similar solved tasks") -> str:
    """Format retrieved hits as a few-shot block to inline in a generation
    prompt. Designed to be human-skim-friendly for the small model."""
    if not hits:
        return ""
    parts = [f"{header} (use as reference, do NOT copy verbatim):\n"]
    for i, h in enumerate(hits, 1):
        parts.append(f"--- Example {i} (similarity {h['score']:.2f}) ---")
        parts.append(f"TASK: {h['desc'].strip()}")
        parts.append(f"SIGIL:\n{h['code'].strip()}\n")
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build / refresh the embedding index")
    b.add_argument("--corpus", default=str(CORPUS_PATH))
    b.add_argument("--out", default=str(INDEX_PATH))
    b.add_argument("--url", default=OLLAMA_URL)
    b.add_argument("--model", default=EMBED_MODEL)

    q = sub.add_parser("query", help="Run a similarity query")
    q.add_argument("text")
    q.add_argument("-k", type=int, default=5)
    q.add_argument("--index", default=str(INDEX_PATH))

    sub.add_parser("stats", help="Show index size + embedding dim")

    args = ap.parse_args()

    if args.cmd == "build":
        build_index(Path(args.corpus), Path(args.out), args.url, args.model)
    elif args.cmd == "query":
        hits = query(args.text, k=args.k, index_path=Path(args.index))
        for i, h in enumerate(hits, 1):
            print(f"[{i}] score={h['score']:.3f}")
            print(f"    desc: {h['desc'][:120]}")
            print(f"    code: {h['code'][:120]}")
            print()
    elif args.cmd == "stats":
        idx = load_index(INDEX_PATH)
        print(f"  count: {idx['count']}")
        print(f"  dim:   {idx['dim']}")
        print(f"  model: {idx['model']}")
        print(f"  src:   {idx['source']}")


if __name__ == "__main__":
    main()
