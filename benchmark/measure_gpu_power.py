#!/usr/bin/env python3
"""Sample GPU package power via amdgpu_top during a benchmark run.

Usage:
    # Start sampling (in another terminal or background):
    python measure_gpu_power.py --out gpu_power.csv --duration 600

    # Then run the benchmark in another terminal:
    python eval_real_tooling.py ...

    # When the benchmark is done, Ctrl-C the sampler and post-process:
    python measure_gpu_power.py --analyze gpu_power.csv

Records GPU package power (Sensors.Average Power, in W) at 1Hz from
amdgpu_top --json. Idle baseline + during-inference incremental are
both captured in the time series; the analyze mode prints both.

Replaces the 180 W estimate in eval_real_tooling.py with measured data.
Sampled at 1 Hz which is fine for the 5-15 s/task workload — the
1-second resolution captures the GPU power state changes.
"""
from __future__ import annotations
import argparse, csv, json, subprocess, sys, time
from pathlib import Path


def sample_loop(out_path: Path, duration_s: int):
    """Sample amdgpu_top once per second; write CSV (timestamp, power_w, gfx_pct)."""
    print(f"Sampling GPU power to {out_path} for {duration_s}s (Ctrl-C to stop early)")
    start = time.time()
    try:
        with out_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "power_w", "gfx_pct", "junction_c"])
            while time.time() - start < duration_s:
                t0 = time.time()
                try:
                    # -d -J: dump mode, single JSON output, exits cleanly.
                    # --no-pc avoids perf-counter overhead. Output is a list
                    # of devices (top-level array).
                    r = subprocess.run(
                        ["amdgpu_top", "-d", "-J", "--no-pc"],
                        capture_output=True, text=True, timeout=4,
                    )
                    d = json.loads(r.stdout)
                    dev = d[0] if isinstance(d, list) else d["devices"][0]
                    sensors = dev["Sensors"]
                    power = sensors.get("Average Power", {}).get("value")
                    if power is None:
                        power = sensors.get("GFX Power", {}).get("value", 0)
                    # --no-pc dump mode does not expose gpu_activity. Fall back
                    # to GFX_SCLK as an active/idle proxy: idle ≤ ~500 MHz,
                    # active boost up to ~2100 MHz on RX 7800 XT.
                    gfx_sclk = sensors.get("GFX_SCLK", {}).get("value", 0)
                    gfx_pct = min(100, int(100 * gfx_sclk / 2100))  # rough proxy
                    junction = sensors.get("Junction Temperature", {}).get("value", 0)
                    w.writerow([round(t0 - start, 2), power, gfx_pct, junction])
                    f.flush()
                except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
                    w.writerow([round(t0 - start, 2), None, None, None])
                    print(f"  warn: {e}", file=sys.stderr)
                # 1 Hz target
                elapsed = time.time() - t0
                if elapsed < 1.0:
                    time.sleep(1.0 - elapsed)
    except KeyboardInterrupt:
        print("\nStopped by user.")


def analyze(path: Path):
    """Print idle baseline + active-period stats from the CSV."""
    samples = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                p = float(row["power_w"])
                g = float(row["gfx_pct"])
                samples.append((p, g))
            except (TypeError, ValueError):
                continue
    if not samples:
        print("no usable samples")
        return
    powers = [p for p, _ in samples]
    gfx = [g for _, g in samples]
    n = len(samples)

    # Heuristic: split into "active" (gfx >= 50%) and "idle" (gfx < 10%) buckets.
    active = [p for p, g in samples if g >= 50]
    idle = [p for p, g in samples if g < 10]

    print(f"Total samples (1 Hz): {n}")
    print(f"Total wall-clock:     {n} s")
    print()
    print(f"Overall average:      {sum(powers)/n:.1f} W")
    print(f"Overall min/max:      {min(powers):.0f} / {max(powers):.0f} W")
    print()
    if idle:
        print(f"Idle samples (GFX <10%):    n={len(idle):3d}  mean={sum(idle)/len(idle):.1f} W")
    if active:
        print(f"Active samples (GFX >=50%): n={len(active):3d}  mean={sum(active)/len(active):.1f} W  "
              f"min/max={min(active):.0f}/{max(active):.0f} W")
    print()
    incremental = (sum(active)/len(active)) - (sum(idle)/len(idle)) if active and idle else None
    if incremental:
        print(f"Active-vs-idle incremental: {incremental:.1f} W")
    print()
    # Energy integral: sum(power_i * 1s) / 3600 = Wh
    total_wh = sum(powers) / 3600
    print(f"Total energy across {n}s: {total_wh:.3f} Wh ({total_wh*1000:.0f} mWh)")
    if active and idle:
        idle_baseline_wh = (sum(idle)/len(idle)) * n / 3600
        gpu_work_wh = total_wh - idle_baseline_wh
        print(f"Idle baseline component:   {idle_baseline_wh:.3f} Wh")
        print(f"Workload-attributable:     {gpu_work_wh:.3f} Wh")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="Output CSV path for sampling mode")
    ap.add_argument("--duration", type=int, default=600,
                    help="Max sampling duration in seconds (default 600)")
    ap.add_argument("--analyze", help="Analyze mode: read CSV and print stats")
    args = ap.parse_args()

    if args.analyze:
        analyze(Path(args.analyze))
    elif args.out:
        sample_loop(Path(args.out), args.duration)
    else:
        ap.error("Provide either --out (record) or --analyze (post-process)")


if __name__ == "__main__":
    main()
