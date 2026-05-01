# Plan: Local Sigil-7B vs Cloud LLMs for tooling-script generation

A deferred experiment to measure whether routing "tooling-script"
workloads (file traversal, text transforms, log filtering, shell-
one-liner replacements) to a local fine-tuned Sigil-7B is a
defensible cost / energy / privacy trade-off versus calling cloud
LLMs for the same work.

## Hypothesis

For agent-shaped tooling tasks where:
- The output is a short standalone script (not a multi-file change)
- The task is run once or in batches (not interactive)
- The expected output is verifiable (run against a sample input)

A locally-hosted fine-tuned 7B + Sigil + RAG + validate-and-retry
loop is competitive with — and on some axes better than — calling
cloud LLMs for the same work.

## Why this matters beyond raw $

Three axes, not just one:

### 1. Direct $ cost

| Setup | Per-call | At 1000 calls/day | At 100K calls |
|---|---|---|---|
| Sonnet (cloud) | ~$0.005 | ~$5/day = ~$1800/yr | ~$500 |
| Opus (cloud) | ~$0.10 | ~$100/day = ~$36K/yr | ~$10000 |
| Local Sigil-7B | $0 marginal | hardware amortized | hardware amortized |

GPU cost (€500 amortized over 2 yr) ≈ €0.68/day. **Break-even
threshold: ~140 Sonnet-replaceable calls/day.**

### 2. Energy / carbon

This axis matters for sustainability AND for any infrastructure where
power is constrained (homelabs, edge, on-prem with capped power).

Rough per-call estimates (orders of magnitude):

| Path | GPU/Compute | Network + DC overhead | Total per call |
|---|---|---|---|
| Sonnet cloud | ~0.5-2 Wh (large model) | ~0.5-2 Wh (HVAC, redundancy, transit) | **~1-4 Wh** |
| Opus cloud | ~2-5 Wh | ~1-3 Wh | **~3-8 Wh** |
| Local Sigil-7B (5 s @ ~180 W) | ~0.25 Wh | negligible | **~0.25-0.4 Wh** |

Local 7B is roughly **5-15× more energy-efficient per call** for
short tasks, simply because:
- The model is smaller (7B vs 200B+ for frontier)
- No data center overhead (HVAC, redundant power, networking)
- No round-trip transit
- The GPU is idle when not in use (no always-on baseline)

Caveat: the comparison is sensitive to *what else the GPU does*.
If a desktop GPU sits idle 22 hours/day for the rest of the time, the
amortized idle power can dominate. If the GPU is shared with other
workloads (gaming, training, inference for other apps), the marginal
energy cost is ~0.25 Wh/call cleanly.

### 3. Privacy / data sovereignty

For tooling-script work specifically:
- File paths, directory structures, env vars, code patterns leave
  the machine on every cloud call
- Internal naming conventions / business logic embedded in tooling
  also leaves
- Cloud providers don't (officially) train on your inputs but the
  data does cross network boundaries and gets logged at multiple
  hops

Local-only generation closes that channel completely. For some
employers or jurisdictions this is the dominant axis (regulatory
compliance, IP protection, classified work).

## Concrete experiment design

### Step 1: collect 30-50 *real* tooling tasks

Not synthetic. Pull from one of:
- `~/.bash_history` / `~/.zsh_history` — shell one-liners ran in the
  last 90 days
- `~/scripts/` or `~/.local/bin/` — small Python/bash utility scripts
- Recent git commits that added small helper scripts

Bucket them:
- File walking / find patterns (~10)
- Log filtering / grep patterns (~10)
- Text transforms (sed / awk replacements) (~10)
- Output formatting / table generation (~5)
- Misc (~5)

For each: capture the original implementation, a known-good test
input, the expected output. The original IS the ground truth.

### Step 2: build the comparison harness

```python
benchmark/eval_tooling_real.py --tasks tooling_tasks.json
```

For each task, run:

A. **Local Sigil-7B + RAG, single shot** — record code, time, output match
B. **Local Sigil-7B + RAG + validate-and-retry once** — record total time, output match
C. **Sonnet, single shot, no RAG** — record code, time, $ cost (compute via tokens × rate)
D. **Opus, single shot, no RAG** — same

Track per-call:
- Pass / fail (output matches)
- Wall-clock seconds
- Token counts (in/out)
- $ cost (cloud paths)
- Wh estimate (compute_seconds × power_draw + DC_overhead)

### Step 3: aggregate and decide

Compute per-bucket and overall:

```
                      A (local 1-shot)  B (local +retry)  C (sonnet)  D (opus)
Pass rate             ?%                ?%                ?%          ?%
Avg latency           ?s                ?s                ?s          ?s
$/call                $0                $0                $0.005      $0.10
Wh/call               0.25              0.4               1.5         5
$/100k calls          $0                $0                $500        $10K
Wh/100k calls         25 kWh            40 kWh            150 kWh     500 kWh
```

Decision tree for routing in production:

- IF task fits the Sigil-expressible bucket AND latency budget ≥ 10 s
  → route to local (path B)
- ELIF task is interactive (latency-sensitive, ≤2 s required)
  → route to Sonnet (path C)
- ELIF task is multi-file or architecture-shaped
  → route to Opus (path D)
- ELSE: cheapest path that meets accuracy threshold

### Step 4: stress-test the deployment story

Once the per-call numbers are in, sanity-check:

1. **Reliability over time**: run the same 30 tasks a week later
   with no changes. Local Sigil should be deterministic; Sonnet
   may drift (model updates, prompt-stripping changes). Capture
   this as part of the case.
2. **Task-bucket coverage**: which buckets does local handle well
   (>80% pass)? Which always need cloud (<50%)? The honest
   deployment story is "route by bucket," not "always local."
3. **Failure cost asymmetry**: when local fails, what does the
   downstream look like? If a tooling script fails silently in
   production, that's worse than a $0.005 cloud cost. Add
   validate-then-only-deploy gates.

## Open questions to address in the experiment

1. **Does the validate-and-retry loop close the 21% wrong-output
   gap?** Our 7B fine-tuned data showed 5/26 failures recovered
   on shot-2. Need fresh data on real tasks.
2. **Do real tooling tasks land in the same accuracy band as the
   synthetic benchmark?** Real tasks may be easier (familiar
   shapes) or harder (novel APIs, unusual edge cases).
3. **Is Sigil's stdlib coverage enough for real tooling?** Memory
   says we have core/ + crypto/ + data/ + db/ + net/ + pattern/ +
   sys/. Need to confirm common tooling needs (HTTP, JSON, regex,
   filesystem walks) all work end-to-end.
4. **Energy estimates need calibration**: actual measurements via
   `perf stat` or wattmeter would replace the order-of-magnitude
   guess.

## What we'd avoid measuring

- Frontier model accuracy (already proven 90%+ in partial Sonnet run)
- Tasks Sigil can't express (out of scope)
- Latency-sensitive interactive paths (different problem)

## Output artifact

A short report like `benchmark/REPORT_local_vs_cloud_tooling.md` with:

- Methodology
- Per-bucket results table
- $ / Wh / privacy three-axis comparison
- A routing recommendation for deployment
- Caveats and open work

## When to run

When:
1. The 7B fine-tune has been validated on the existing 100-task suite (DONE)
2. There's a real workload to draw 30+ tooling tasks from
3. ~3 hours is available for setup + comparison runs

This is a deferred experiment, not a blocker on the current
benchmark/comparison work.
