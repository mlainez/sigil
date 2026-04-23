#!/usr/bin/env python3
"""Analyze benchmark results and produce comparison tables."""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict


def load_results(paths: list[str]) -> list[dict]:
    """Load and merge results from multiple JSON files."""
    all_results = []
    for p in paths:
        data = json.loads(Path(p).read_text())
        model = data["meta"]["model"]
        for r in data["results"]:
            r["_model"] = model
            all_results.append(r)
    return all_results


def get_tier(task_id: str) -> int:
    num = int(task_id.split("_")[0])
    if num <= 3:
        return 1
    elif num <= 7:
        return 2
    else:
        return 3


def print_model_comparison(results: list[dict]):
    """Compare languages within each model."""
    # Group by model
    by_model = defaultdict(list)
    for r in results:
        by_model[r["_model"]].append(r)

    for model, model_results in sorted(by_model.items()):
        print(f"\n{'=' * 70}")
        print(f"MODEL: {model}")
        print(f"{'=' * 70}")

        by_lang = defaultdict(list)
        for r in model_results:
            by_lang[r["language"]].append(r)

        # Header
        langs = sorted(by_lang.keys())
        header = f"{'Metric':<30}"
        for lang in langs:
            header += f"  {lang:>12}"
        print(header)
        print("-" * len(header))

        # Runs
        row = f"{'Runs':<30}"
        for lang in langs:
            row += f"  {len(by_lang[lang]):>12}"
        print(row)

        # First-attempt correctness
        row = f"{'First-attempt correct':<30}"
        for lang in langs:
            lr = by_lang[lang]
            n = len(lr)
            c = sum(1 for r in lr if r["first_attempt_correct"])
            row += f"  {f'{c}/{n} ({100*c//n}%)':>12}"
        print(row)

        # Final correctness
        row = f"{'Final correct (after retries)':<30}"
        for lang in langs:
            lr = by_lang[lang]
            n = len(lr)
            c = sum(1 for r in lr if r["final_correct"])
            row += f"  {f'{c}/{n} ({100*c//n}%)':>12}"
        print(row)

        # Avg total tokens
        row = f"{'Avg total tokens':<30}"
        for lang in langs:
            lr = by_lang[lang]
            avg = sum(r["total_tokens"] for r in lr) / len(lr)
            row += f"  {avg:>12.0f}"
        print(row)

        # Avg prompt tokens
        row = f"{'Avg prompt tokens':<30}"
        for lang in langs:
            lr = by_lang[lang]
            avg = sum(r["total_prompt_tokens"] for r in lr) / len(lr)
            row += f"  {avg:>12.0f}"
        print(row)

        # Avg completion tokens
        row = f"{'Avg completion tokens':<30}"
        for lang in langs:
            lr = by_lang[lang]
            avg = sum(r["total_completion_tokens"] for r in lr) / len(lr)
            row += f"  {avg:>12.0f}"
        print(row)

        # Avg attempts
        row = f"{'Avg attempts to correct':<30}"
        for lang in langs:
            lr = by_lang[lang]
            avg = sum(r["attempts_to_correct"] for r in lr) / len(lr)
            row += f"  {avg:>12.1f}"
        print(row)

        # Per-tier breakdown
        print(f"\n  Per-tier first-attempt correctness:")
        for tier in [1, 2, 3]:
            row = f"    Tier {tier}:{'':>22}"
            for lang in langs:
                lr = [r for r in by_lang[lang] if get_tier(r["task_id"]) == tier]
                n = len(lr)
                if n == 0:
                    row += f"  {'N/A':>12}"
                else:
                    c = sum(1 for r in lr if r["first_attempt_correct"])
                    row += f"  {f'{c}/{n} ({100*c//n}%)':>12}"
            print(row)

        # Per-task detail
        print(f"\n  Per-task detail:")
        tasks = sorted(set(r["task_id"] for r in model_results))
        for task_id in tasks:
            tier = get_tier(task_id)
            row = f"    T{tier} {task_id:<24}"
            for lang in langs:
                lr = [r for r in by_lang[lang] if r["task_id"] == task_id]
                if not lr:
                    row += f"  {'—':>12}"
                else:
                    c = sum(1 for r in lr if r["first_attempt_correct"])
                    avg_tok = sum(r["total_tokens"] for r in lr) / len(lr)
                    row += f"  {f'{c}/{len(lr)} {avg_tok:.0f}t':>12}"
            print(row)


def print_cross_model(results: list[dict]):
    """Compare the same language across different models."""
    by_lang = defaultdict(list)
    for r in results:
        by_lang[r["language"]].append(r)

    for lang, lang_results in sorted(by_lang.items()):
        print(f"\n{'=' * 70}")
        print(f"LANGUAGE: {lang.upper()} — cross-model comparison")
        print(f"{'=' * 70}")

        by_model = defaultdict(list)
        for r in lang_results:
            by_model[r["_model"]].append(r)

        models = sorted(by_model.keys())
        header = f"{'Metric':<30}"
        for m in models:
            short = m[:15]
            header += f"  {short:>15}"
        print(header)
        print("-" * len(header))

        row = f"{'First-attempt correct':<30}"
        for m in models:
            mr = by_model[m]
            n = len(mr)
            c = sum(1 for r in mr if r["first_attempt_correct"])
            row += f"  {f'{c}/{n} ({100*c//n}%)':>15}"
        print(row)

        row = f"{'Avg total tokens':<30}"
        for m in models:
            mr = by_model[m]
            avg = sum(r["total_tokens"] for r in mr) / len(mr)
            row += f"  {avg:>15.0f}"
        print(row)

        row = f"{'Avg attempts':<30}"
        for m in models:
            mr = by_model[m]
            avg = sum(r["attempts_to_correct"] for r in mr) / len(mr)
            row += f"  {avg:>15.1f}"
        print(row)


def print_token_savings(results: list[dict]):
    """Show token savings of Sigil vs each other language, per task."""
    sigil_results = [r for r in results if r["language"] == "sigil"]
    other_langs = set(r["language"] for r in results) - {"sigil"}

    if not sigil_results or not other_langs:
        return

    for other_lang in sorted(other_langs):
        other_results = [r for r in results if r["language"] == other_lang]
        print(f"\n{'=' * 70}")
        print(f"TOKEN SAVINGS: Sigil vs {other_lang.upper()}")
        print(f"{'=' * 70}")

        # Group by (model, task_id)
        sigil_by_key = defaultdict(list)
        other_by_key = defaultdict(list)
        for r in sigil_results:
            sigil_by_key[(r["_model"], r["task_id"])].append(r)
        for r in other_results:
            other_by_key[(r["_model"], r["task_id"])].append(r)

        total_sigil = 0
        total_other = 0
        count = 0

        print(f"{'Model + Task':<40}  {'Sigil':>8}  {other_lang:>8}  {'Delta':>8}  {'%':>6}")
        print("-" * 75)

        for key in sorted(set(sigil_by_key.keys()) & set(other_by_key.keys())):
            model, task_id = key
            s_avg = sum(r["total_tokens"] for r in sigil_by_key[key]) / len(sigil_by_key[key])
            o_avg = sum(r["total_tokens"] for r in other_by_key[key]) / len(other_by_key[key])
            delta = s_avg - o_avg
            pct = (delta / o_avg * 100) if o_avg else 0
            total_sigil += s_avg
            total_other += o_avg
            count += 1
            short_model = model[:20]
            print(f"  {short_model} / {task_id:<15}  {s_avg:>8.0f}  {o_avg:>8.0f}  {delta:>+8.0f}  {pct:>+5.1f}%")

        if count > 0:
            delta_total = total_sigil - total_other
            pct_total = (delta_total / total_other * 100) if total_other else 0
            print("-" * 75)
            print(f"  {'TOTAL':<37}  {total_sigil:>8.0f}  {total_other:>8.0f}  {delta_total:>+8.0f}  {pct_total:>+5.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Analyze benchmark results")
    parser.add_argument("files", nargs="+", help="Result JSON files to analyze")
    parser.add_argument("--cross-model", action="store_true",
                        help="Show cross-model comparison for each language")
    parser.add_argument("--token-savings", action="store_true",
                        help="Show token savings of Sigil vs other languages")
    args = parser.parse_args()

    results = load_results(args.files)
    print(f"Loaded {len(results)} result entries from {len(args.files)} file(s)\n")

    print_model_comparison(results)

    if args.cross_model:
        print_cross_model(results)

    if args.token_savings:
        print_token_savings(results)


if __name__ == "__main__":
    main()
