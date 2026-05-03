"""Router: decide whether a task goes to local Sigil or to a cloud LLM.

This is the parent-agent-side helper called by orchestrators (Claude Code,
opencode, custom harnesses) to triage incoming tasks. The router is
deliberately a small heuristic — not a learned classifier — because the
deployment story is "local for tooling shapes, cloud for everything else"
and that decision rule fits in a few dozen lines.

Decision rule
=============

Inputs: task description (free text), latency budget (seconds), and a
privacy flag indicating whether the input data is sensitive enough that
shipping it to a cloud provider is a hard NO.

Outputs: one of
  - "local"           — route to the sigil-tooling sub-agent
  - "cloud"           — route to the cloud orchestrator directly
  - "cloud_required_for_privacy"
                      — task is not local-shaped AND data is sensitive;
                        the caller must escalate to a human or accept
                        sub-optimal local handling

Local is preferred whenever:
  (a) the task fits one of the LOCAL_SHAPES and
  (b) the latency budget is at least ~2 seconds (local 7B inference floor).

Cloud is preferred whenever:
  - The shape is in CLOUD_REQUIRED_SHAPES (architecture, multi-file
    refactor, library research, etc.), OR
  - The latency budget is sub-second-interactive, OR
  - The shape doesn't classify into either bucket.

Privacy is the override: if the data is sensitive and the shape can be
expressed locally, force local even at accuracy cost. If the data is
sensitive and the shape *can't* be expressed locally, the router refuses
to silently fall back to cloud.

Performance characteristics are documented in `agent_workflow/README.md`
and `benchmark/STREAM_C_RESULT.md` (29/30 on Stream C tooling tasks; 0$
marginal cost; ~5-15 s/call wall time).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Route(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    CLOUD_REQUIRED_FOR_PRIVACY = "cloud_required_for_privacy"


# Shapes the local Sigil ensemble can express well. Source: the 30-task
# Stream C suite, which the v6+phi-v2 ensemble solves at 29/30 (see
# benchmark/STREAM_C_RESULT.md).
LOCAL_SHAPES = frozenset({
    "file_walk",
    "log_parse",
    "text_transform",
    "csv_parse",
    "tsv_parse",
    "json_path_extract",
    "config_parse",
    "format_output",
    "scan_with_state",
    "string_manipulation",
    "numeric_aggregation",
    "regex_extract",
    "regex_validate",
    "count_aggregation",
    "sort_top_n",
    "dedup",
    "split_join",
    "permission_format",
    "ipv4_validate",
})

# Shapes that require cloud frontier capability. Sigil cannot express
# these well today and the local ensemble has no advantage.
CLOUD_REQUIRED_SHAPES = frozenset({
    "multi_file_refactor",
    "architecture_design",
    "library_research",
    "interactive_chat",
    "non_sigil_language",
    "code_review",
    "doc_synthesis",
    "test_authoring_with_imports",
})


# Heuristic classifier: token-anchor patterns ordered by specificity.
# The first match wins; "unknown" if nothing matches. Tuned against the
# Stream C and agent_tasks.json corpora — see tests at the bottom.
_SHAPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("multi_file_refactor",
     re.compile(r"\b(refactor|redesign|across multiple files|repo-wide|codebase[- ]wide)\b", re.I)),
    ("architecture_design",
     re.compile(r"\b(architect(ure)?|api design|system design|module boundary)\b", re.I)),
    ("library_research",
     re.compile(r"\b(which library|recommend.*(library|package|crate|gem)|compare.*frameworks?)\b", re.I)),
    ("interactive_chat",
     re.compile(r"\b(explain|summari[sz]e|describe.*for a (junior|new))\b", re.I)),
    ("doc_synthesis",
     re.compile(r"\b(generate (docs|documentation)|write a readme)\b", re.I)),
    ("code_review",
     re.compile(r"\b(review (this|the) (pr|patch|diff)|security review)\b", re.I)),
    ("test_authoring_with_imports",
     re.compile(r"\bwrite (unit |integration )?tests?\b.*\b(framework|pytest|jest|junit)", re.I)),
    ("regex_extract",
     re.compile(r"\b(extract|find all|grep)\b.*\b(regex|pattern|emails?|urls?|ips?|dates?)\b", re.I)),
    ("ipv4_validate",
     re.compile(r"\b(valid(ate)?|check)\b.*\bipv?4?\b", re.I)),
    ("permission_format",
     re.compile(r"\b(permission|chmod|octal|symbolic|rwx)\b", re.I)),
    ("json_path_extract",
     re.compile(r"\b(json|jq|path).*\b(extract|select|get)\b", re.I)),
    ("csv_parse",
     re.compile(r"\b(csv|comma[- ]separated)\b", re.I)),
    ("tsv_parse",
     re.compile(r"\b(tsv|tab[- ]separated)\b", re.I)),
    ("file_walk",
     re.compile(r"\b(walk|traverse|find files|find\b.*-name|recursive(ly)?)\b", re.I)),
    ("log_parse",
     re.compile(r"\b(log|nginx access|syslog|grep|filter lines)\b", re.I)),
    ("count_aggregation",
     re.compile(r"\b(count|frequency|how many|tally|histogram)\b", re.I)),
    ("sort_top_n",
     re.compile(r"\b(sort|top \d+|n largest|descending|ascending)\b", re.I)),
    ("dedup",
     re.compile(r"\b(dedup(licate)?|unique(s|d)?|distinct)\b", re.I)),
    ("split_join",
     re.compile(r"\b(split|join|tokeni[sz]e|concatenate)\b", re.I)),
    ("text_transform",
     re.compile(r"\b(replace|substitute|uppercase|lowercase|transform|squeeze|collapse)\b", re.I)),
    ("format_output",
     re.compile(r"\b(format|markdown table|emit|print as|render as)\b", re.I)),
    ("string_manipulation",
     re.compile(r"\b(strip|trim|pad|prefix|suffix)\b", re.I)),
    ("numeric_aggregation",
     re.compile(r"\b(sum|average|mean|median|min|max)\b.*\b(values|column|rows?)\b", re.I)),
    ("scan_with_state",
     re.compile(r"\b(running total|state machine|scan|fold|accumulate)\b", re.I)),
]


def classify_shape(description: str) -> str:
    """Return a shape label or 'unknown'. Token-anchor heuristic; replace
    with a learned classifier later if needed."""
    for label, pat in _SHAPE_PATTERNS:
        if pat.search(description):
            return label
    return "unknown"


@dataclass(frozen=True)
class RoutingDecision:
    route: Route
    shape: str
    reason: str


def route_task(
    description: str,
    *,
    latency_budget_seconds: float = 30.0,
    privacy_required: bool = False,
) -> RoutingDecision:
    """Decide where the task goes.

    The order of checks matters: privacy overrides everything, then
    latency, then cloud-required shapes, then local-eligible shapes,
    then a default.
    """
    shape = classify_shape(description)

    if privacy_required:
        if shape in LOCAL_SHAPES:
            return RoutingDecision(
                Route.LOCAL, shape,
                "privacy required and shape is local-expressible",
            )
        return RoutingDecision(
            Route.CLOUD_REQUIRED_FOR_PRIVACY, shape,
            "privacy required but shape is not local-expressible — escalate",
        )

    if latency_budget_seconds < 2.0:
        return RoutingDecision(
            Route.CLOUD, shape,
            f"latency budget {latency_budget_seconds:.1f}s below local 7B floor (~2s)",
        )

    if shape in CLOUD_REQUIRED_SHAPES:
        return RoutingDecision(
            Route.CLOUD, shape,
            f"shape '{shape}' requires cloud capability",
        )

    if shape in LOCAL_SHAPES:
        return RoutingDecision(
            Route.LOCAL, shape,
            f"shape '{shape}' is in local-eligible set",
        )

    return RoutingDecision(
        Route.CLOUD, shape,
        f"shape '{shape}' did not classify; defaulting to cloud",
    )


# ============================================================================
# Self-test: minimal coverage of the rule table. Run with `python router.py`.
# ============================================================================

def _selftest() -> None:
    cases = [
        # (description, latency, privacy_required) -> expected route
        ("Extract every email address from this log file", 30.0, False, Route.LOCAL),
        ("Walk the project tree and list all .py files modified in the last 7 days",
         30.0, False, Route.LOCAL),
        ("Parse this CSV and print the top 3 categories by amount", 30.0, False, Route.LOCAL),
        ("Write a Markdown table from this TSV", 30.0, False, Route.LOCAL),
        ("Count ERROR lines per hour in nginx access logs", 30.0, False, Route.LOCAL),
        ("Validate this IPv4 address", 30.0, False, Route.LOCAL),
        ("Refactor this auth module across all five files", 30.0, False, Route.CLOUD),
        ("Recommend a JSON parsing library for Rust", 30.0, False, Route.CLOUD),
        ("Explain how the event loop works in Node.js", 30.0, False, Route.CLOUD),
        ("Filter lines containing this regex pattern", 0.5, False, Route.CLOUD),
        ("Extract emails from this log", 30.0, True, Route.LOCAL),
        ("Refactor the entire auth module", 30.0, True, Route.CLOUD_REQUIRED_FOR_PRIVACY),
        ("Do something completely vague and unmappable", 30.0, False, Route.CLOUD),
    ]
    fails = []
    for desc, lat, priv, expected in cases:
        d = route_task(desc, latency_budget_seconds=lat, privacy_required=priv)
        ok = d.route is expected
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {desc[:55]:55s} -> {d.route.value} ({d.shape})")
        if not ok:
            fails.append((desc, d, expected))
    if fails:
        print(f"\n{len(fails)} case(s) failed:")
        for desc, d, expected in fails:
            print(f"  {desc!r}: got {d.route.value} ({d.shape}; {d.reason}); expected {expected.value}")
        raise SystemExit(1)
    print(f"\nAll {len(cases)} routing cases pass.")


if __name__ == "__main__":
    _selftest()
