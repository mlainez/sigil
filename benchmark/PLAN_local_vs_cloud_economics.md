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

### 2. Energy / carbon — sourced estimates with uncertainty bounds

This axis matters for sustainability AND for any infrastructure where
power is constrained (homelabs, edge, on-prem with capped power).
**Earlier drafts of this document used unsourced point estimates that
made the local path look unambiguously greener. The numbers below are
based on published peer-reviewed measurements and are bracketed by
uncertainty bounds, not optimised for either side.**

#### The test rig (so the local numbers are reproducible)

| Component | Spec | Notes |
|---|---|---|
| **GPU** | AMD Radeon RX 7800 XT 16 GB | GFX1101 / Navi32, RDNA3, 60 CUs, 32.6 TFLOPS FP32 |
| GPU power cap (this unit) | **212 W current, 244 W max** | Read live via `amdgpu_top` (manufacturer TBP marketing is 263 W, not enforced) |
| GPU idle baseline | **~32 W** | Measured via `amdgpu_top` with display attached, no inference |
| **CPU** | AMD Ryzen 7 7800X3D | 8C/16T, 96 MB L3 |
| **RAM** | 64 GB DDR5 | |
| **OS** | Ubuntu 24.04.4 LTS, kernel 6.19.10 | |
| **Drivers** | ROCm via `bitsandbytes-rocm`, `HSA_OVERRIDE_GFX_VERSION=11.0.0` | Override needed because gfx1101 (Navi32) is not on the bnb supported list |

All local-side energy figures below are **GPU package power** read
from `amdgpu_top` (the same hardware sensors the driver uses for
thermal management). Plug-side draw adds ~80-120 W of CPU + RAM +
motherboard + display, which we exclude as a wash with the cloud
customer's terminal load. The `benchmark/measure_gpu_power.py`
sampler runs alongside the eval harness and records 1 Hz power
samples; raw CSV + analysis output are part of the test artifacts.

#### Sources (peer-reviewed measurements only)

1. **Luccioni, Jernite & Strubell (2024)** — "[Power Hungry Processing:
   Watts Driving the Cost of AI Deployment?](https://dl.acm.org/doi/10.1145/3630106.3658542)"
   ACM FAccT '24. ([arXiv preprint](https://arxiv.org/abs/2311.16863) /
   [paper PDF](https://facctconference.org/static/papers24/facct24-6.pdf))
   Measures actual GPU energy across model sizes on real text-gen tasks.
   **Table 5**: per-inference energy ranges from **5.4×10⁻⁵ kWh
   (~0.054 Wh) for BLOOMz-560M up to 1.0×10⁻⁴ kWh (~0.10 Wh) for
   BLOOMz-7B**, on a batched-inference benchmark (batch size and
   token counts described in §4 of the paper).

2. **Samsi et al. (2023)** — "[From Words to Watts: Benchmarking the
   Energy Costs of LLM Inference](https://arxiv.org/abs/2310.03003)"
   (MIT Lincoln Lab, IEEE HPEC '23). Measured LLaMA-65B inference at
   **~3-4 joules per output token** (= 0.83-1.11 Wh per 1K output
   tokens) on V100/A100 GPUs. Methodology: nvidia-smi sampled at
   100 ms intervals + DCGM aggregate energy in joules; batch size 64,
   max output 256 tokens; sharded inference on 4×A100 or 8-32×V100.

3. **Coignion, Quinton et al. (2025)** — "[From Prompts to Power:
   Measuring the Energy Footprint of LLM Inference](https://arxiv.org/abs/2511.05597)"
   ([PDF](https://arxiv.org/pdf/2511.05597)). Reports **LLaMA-405B
   inference: 21.7 Wh for a single prompt; 60.4 Wh for batch of 100
   in 29.4 seconds**. Critical finding for our analysis: **batching
   reduces per-prompt energy by ~36×** at this scale.

4. **TokenPowerBench (December 2025)** — "[TokenPowerBench: Benchmarking
   the Power Consumption of LLM Inference](https://arxiv.org/abs/2512.03024)"
   ([HTML](https://arxiv.org/html/2512.03024v1)). The most comprehensive
   recent benchmark, covering Llama, Falcon, Qwen, Mistral from 1B to
   Llama3-405B. Reports per-token energy and the **~7.3× per-token
   energy growth from 1B to 70B (Llama-3)** despite a 70× parameter
   growth — i.e. memory bandwidth, not parameter count, dominates.
   Specific 8B-class measurement: **0.12-0.20 J per output token =
   0.033-0.056 Wh per 1K out tokens** (lower at batch 64, higher at
   batch 1).

5. **Patterson et al. (2021)** — "[Carbon Emissions and Large Neural
   Network Training](https://arxiv.org/abs/2104.10350)" (Google).
   Notes hyperscale PUE is "**~1.4-2× more efficient than typical
   datacenters**." Recent Google sustainability reports (2024) put
   their fleet PUE at **1.09-1.10**; we use **1.10** as a conservative
   hyperscale-cloud multiplier in this document.

6. **Aslan et al. (2018)** — "[Electricity Intensity of Internet Data
   Transmission: Untangling the Estimates](https://onlinelibrary.wiley.com/doi/full/10.1111/jiec.12630)"
   (Journal of Industrial Ecology). Network transit energy ~0.06 kWh/GB
   for residential broadband (2015); halving every ~2 years per Koomey
   means ≈0.01-0.02 kWh/GB today. For a typical 5KB tooling-task
   request + response: **≈0.0001 Wh per call. Negligible** at this
   workload — drop from the accounting.

7. **AMD Radeon RX 7800 XT** ([spec page](https://www.amd.com/en/products/graphics/desktops/radeon/7000-series/amd-radeon-rx-7800-xt.html))
   — the actual GPU on this test rig. Specifications:
   - ASIC: **GFX1101 / Navi32** (RDNA3, gfx1100-family via
     `HSA_OVERRIDE_GFX_VERSION=11.0.0`)
   - VRAM: **16 GB GDDR6**, 256-bit bus, 624 GB/s peak bandwidth
   - Compute: **32.6 TFLOPS FP32 peak**, 60 CUs at 2.124 GHz boost
   - Power cap on this unit (read live from `amdgpu_top`):
     **current 212 W / max 244 W**. AMD's marketing TBP of 263 W is
     not enforced here.
   - Idle baseline (measured `amdgpu_top --json -J` with display
     attached, no inference): **~32 W GFX power**.
   - Third-party sustained-load measurements
     ([TechPowerUp review](https://www.techpowerup.com/review/sapphire-radeon-rx-7800-xt-pulse/),
     [Tom's Hardware review](https://www.tomshardware.com/reviews/amd-radeon-rx-7800-xt))
     report **150-200 W during compute-bound work**. Earlier drafts
     used 180 W as a midpoint estimate; the new `measure_gpu_power.py`
     captures real data instead.

   **Test rig specifics:**
   - CPU: AMD Ryzen 7 7800X3D (8C/16T, 96MB L3, ~120 W TDP at boost)
   - RAM: 64 GB DDR5
   - GPU: AMD Radeon RX 7800 XT 16 GB (specs above)
   - OS: Ubuntu 24.04.4 LTS (Linux 6.19.10)
   - Python 3.12 + ROCm via bitsandbytes-rocm
   - Single-user desktop, no other GPU workloads during tests
   - Power readings reported below are GPU-package only via
     `amdgpu_top`, NOT plug-side. Plug-side adds an estimated 80-120 W
     of CPU + RAM + motherboard + display draw which is approximately
     the same as a typical cloud-customer terminal would draw, so it
     does not affect the comparative analysis.

8. **Anthropic / OpenAI / Google do not publish per-call energy for
   production inference.** Sonnet, GPT-4, Gemini bracketing therefore
   uses Samsi 2023 + Coignion 2025 + TokenPowerBench 2025 measured
   ranges by parameter class. We treat any specific Sonnet number as
   a range, not a point estimate.

#### Measured baseline — REAL GPU power data (Stream C v5+phi run)

These numbers are from a Stream C 30-task run with `measure_gpu_power.py`
sampling `amdgpu_top` at 1 Hz. Power readings are GPU package power
(matches what hyperscalers measure for their own carbon accounting).
Result CSV: `benchmark/power_logs/v5_ensemble_stream_c.csv`.

| Metric | Measured value |
|---|---|
| Total sampling window | 347 s (incl ~30 s idle baseline at start) |
| Eval execution window | ~242 s for 30 tasks (avg 8.07 s/task) |
| **Idle GPU power, model warm in VRAM** | **39.8 W mean** |
| **Active inference power** | **167.9 W mean (range 53-229 W)** |
| Active-vs-idle incremental | 128.1 W |
| Total energy across full window | 14.92 Wh |
| Idle baseline component | 3.83 Wh |
| **Workload-attributable energy** | **11.09 Wh for 30 tasks** = **0.370 Wh/task** |

Earlier estimates used 180 W mean inference power (× wallclock seconds);
the **measured** mean is **~168 W**, so the estimate was within 7% of
truth. Per-task energy estimate was 0.382 Wh; measured 0.370 Wh.
The "180 W × seconds" estimate was conservative-high by ~3% — close
enough that earlier conclusions remain stable, but now backed by data.

Cloud comparison numbers (from `benchmark/stream_c_v4_phi_fresh25.json`):

| Metric | Value |
|---|---|
| Cloud Sonnet per task (avg) | **3 input + 51 output tokens**, **2-4 s** end-to-end |
| Cloud Sonnet per task at $-pricing | **\$0.0008/task** (the only number we can verify directly) |
| Local Sigil ensemble per task (measured) | **0.370 Wh** |

Sonnet's actual energy is *unknown* because Anthropic doesn't publish
inference-energy figures. Bracketing it with Samsi 2023's measured
ranges:

```
Cloud_Wh = (input_tok × 0.04 + output_tok × X) / 1000 × 1.15
where X = energy per 1K output tokens (depends on model size)
```

For our average task (3 input / 51 output tokens), using **measured**
numbers from the cited papers (no extrapolation past where the source
goes):

| If Sonnet's effective active-param size is… | X (Wh per 1K out) | Source for X | Cloud Wh / call |
|---|---|---|---|
| 7B-class | **0.04** | TokenPowerBench Llama-8B at batch ≥64 | **0.0026** |
| 7B-class (cold, batch 1) | **0.06** | TokenPowerBench Llama-8B batch 1 | **0.0036** |
| 11B-class | **0.10** | Luccioni 2024 Table 5 BLOOMz-7B (single inference) | **0.0058** |
| 65-70B-class | **0.83-1.11** | Samsi 2023 LLaMA-65B (3-4 J/token) | **0.049-0.065** |
| 405B-class | **~5-15** | Coignion 2025 (LLaMA-405B 21.7 Wh single prompt; assumes ~250 out tokens, batch 1) | **~0.30-0.85** |

Local Sigil ensemble is **0.382 Wh/call** (the same number for any of
these scenarios — it doesn't change with the cloud model size).

**Even at the LLaMA-405B-class end of the spectrum, cloud is still
energy-comparable-or-better than local on this workload.** That's the
strict reading of the measured peer-reviewed data we have.

#### The breakeven calculation

Local matches cloud when:

```
0.382 Wh = (3 × 0.04 + 51 × X) / 1000 × 1.10
0.382 / 1.10 = 0.347 ≈ (0.12 + 51X) / 1000
X ≈ 6.8 Wh per 1K output tokens
```

So **on the average Stream C task (51 output tokens) at 7.64 s local
wallclock**, local matches cloud only if Sonnet's measured per-token
energy is ~6.8 Wh/1K output. The **measured ceiling in published
literature** ([Coignion 2025](https://arxiv.org/abs/2511.05597) on
LLaMA-405B at batch 1) is around 5-15 Wh/1K output for the LARGEST
publicly-benchmarked model — and that's measured, not extrapolated.

**Verdict at this task profile:** local-Sigil-7B is **likely less
energy-efficient than cloud Sonnet** at the volumes / batch sizes
hyperscalers run. The cloud advantage is two-fold:

1. **Lower per-token energy from batching.** Coignion 2025 shows
   ~36× per-prompt energy reduction when batching 100 prompts vs
   single. Hyperscale inference batches dozens to hundreds of
   prompts; consumer-local typically batches 1.
2. **Frontier-model amortization.** Even a 405B-class cloud model
   (~21 Wh/single) only matches local at batch 1; in production
   batches that drops to ~0.6 Wh/prompt, well below local.

#### Where local DOES win — the breakeven points

The picture changes dramatically when any of three variables shifts:

**(a) Longer outputs.** Local Wh scales sub-linearly with output
length (most of 7.64 s is fixed orchestration: RAG retrieval, prompt
prep, retry, Sigil execution; only ~1-2 s is generation for short
outputs). Cloud Wh scales linearly with output. For an N-output-token
task, with local incremental rate ~0.005 Wh per 100 generated tokens
(≈ 100 tok/s on RDNA3 at 180 W) plus a ~0.30 Wh fixed orchestration
cost:

```
Local_Wh   ≈ 0.30 + 0.0005 × N
Cloud_Wh   ≈ (3 × 0.04 + N × X) / 1000 × 1.10
```

Setting equal and solving for the **output-length breakeven** at a
given Sonnet class X (Wh/1K output, **measured values from cited
papers**):

| Sonnet class assumption | X (Wh/1K out) | Source | Output tokens for local to win |
|---|---|---|---|
| 7B-class (batched) | 0.04 | TokenPowerBench | **never** at this orchestration overhead |
| 11B-class (batched) | 0.10 | Luccioni 2024 BLOOMz-7B | **never** (X < local incremental rate) |
| 65-70B-class (batched, A100) | 0.85 | Samsi 2023 (mid of 3-4 J/token) | **~390 output tokens** |
| 70B-class (batch 1, worst case) | 1.5 | Samsi 2023 high end | **~210 output tokens** |
| 405B-class (batch 1) | 6.8 | Coignion 2025 LLaMA-405B / 250 out | **~46 output tokens** |
| 405B-class (batched at hyperscale) | 0.6 | Coignion 2025 batch-100 derived | **~600 output tokens** |

The Stream C tasks averaged 51 output tokens. **For this short-output
workload, local is energy-disadvantaged across the entire measured
range of cloud configurations except possibly LLaMA-405B-class at
batch 1** (which is not how production hyperscale inference is
served).

For long-output synthesis tasks (300+ tokens), **local becomes
energy-favourable when Sonnet is ≥70B-class**, but not before.

**(b) Lower local wallclock.** Half of the local 7.64 s is the
3-attempt retry loop and ensemble fallback. A solo v4 run hits 5 s
and 0.25 Wh/call. Skipping retry saves ~0.13 Wh/call but costs ~5 pp
of accuracy. The ensemble path also loads BOTH Qwen-Sigil-v4 (5 GB)
AND Phi-Sigil-v1 (8.8 GB) which thrashes VRAM swaps; v2-only path on
the same suite yields ~6 s/call → 0.30 Wh/call → breakeven moves
~20% in local's favor.

**(c) Batched local inference.** [Coignion 2025](https://arxiv.org/abs/2511.05597)
shows the **batching effect is the most important variable in the
calculation**, with ~36× per-prompt energy reduction at batch 100 vs
batch 1 on LLaMA-405B. Local single-user inference batches 1; cloud
hyperscale typically batches 32-128. **This batching gap is the
single largest source of cloud's per-call energy advantage** —
larger than the model-size penalty cloud pays for being frontier-
class.

#### Honest summary

| Workload shape | Energy verdict |
|---|---|
| Short-output tooling tasks (50-100 out tokens), Sonnet 7-70B-equiv (batched) | **Cloud wins** by 5-100× per call (measured peer-reviewed range) |
| Short-output tooling tasks, Sonnet ≥405B-class single-prompt (batch 1) | **Roughly tied** (~0.4 Wh local vs ~0.4-0.7 Wh cloud) |
| Long-output synthesis (300+ out tokens), Sonnet ≥70B-class | **Local wins** if cloud is single-prompt; cloud still wins at typical hyperscale batch sizes |
| High-volume single-user (e.g. 100 calls/day) at home, no idle penalty | **Local wins** as orchestration overhead amortizes over 1 GPU spin-up |
| The Coignion 2025 batch-100 finding | **Cloud has a fundamental ~36× batching advantage** on the same hardware that's hard to overcome at single-user volume |

The Stream C deployment-shape workload (short outputs, decision-grade
single-attempt accuracy) sits in the most cloud-favourable corner of
this matrix. **For that specific workload, the honest energy claim is
that cloud is likely 2-20× more energy-efficient per call, with
uncertainty primarily in Sonnet's actual class.** The pillars of the
local case are therefore **cost (~$0.0008 vs $0)** and
**confidentiality (network channel closed entirely)**, not energy.

This is a real, measurable shift in the local-LLM narrative: the
"local is greener" intuition is **wrong for short single-user
workloads** at this hardware tier. Local becomes greener only when
batching converges (high-volume self-hosted serving) or when outputs
grow long enough that orchestration overhead amortizes.

#### What would tighten the bracket

1. **Read AMD GPU power directly via `amdgpu_top`** during a Stream C
   run. The `amdgpu_top` utility reports real-time GPU package power
   in watts on RDNA3 (sourced from the same hardware sensors the
   driver uses for thermal management). Sampling at 1 Hz across a
   30-task run captures both idle baseline and during-inference
   incremental — directly replaces the 180 W estimate with a measured
   average. Run as `amdgpu_top --json` during inference and post-
   process the time-series. **This is the single most impactful
   refinement available with no extra hardware.**
2. **Wall-plug wattmeter** to capture system-level draw including
   CPU, RAM, motherboard, fans. `amdgpu_top` covers GPU package only;
   plug-side captures everything. Useful as a sanity check on the
   GPU-only number.
3. **Anthropic / OpenAI publishing per-call energy figures.** Highly
   unlikely in the next year; treat as fixed.
4. **Replicating Samsi 2023's methodology on RX 7800 XT** for our
   specific Qwen2.5-Coder-7B-Instruct + Phi-Sigil ensemble. ~1 day of
   work; would replace the bracket with a measured per-token figure
   for our specific configuration. Combine with #1 for full per-call
   accounting.

The `amdgpu_top` route (#1) is the **fastest path to a defensible
number** — it can be done in an afternoon by running the Stream C
suite while logging GPU package power, then averaging across tasks.
Recommended next step before any final paper claim.

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
