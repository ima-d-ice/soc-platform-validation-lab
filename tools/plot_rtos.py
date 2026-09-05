#!/usr/bin/env python3
"""Plot Phase-6 RTOS results from the real benchmark JSON.

Reads results/rtos_scheduling.json (rep means in summary) and writes 7
PNGs to results/plots/. Fails loudly on missing data. All values are
measured/derived from the virtual SoC + scheduler model ticks.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "results" / "rtos_scheduling.json"
DEFAULT_OUT = ROOT / "results" / "plots"


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot Phase-6 RTOS results.")
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.input).read_text())
    summary: dict = data["summary"]
    if not summary:
        raise SystemExit(f"plot_rtos: no summary in {args.input}")
    names = list(summary.keys())
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    def save(name):
        p = outdir / name
        plt.tight_layout()
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"wrote {p}")

    def bar(names, vals, ylabel, title, fname, rotation=30):
        plt.figure(figsize=(11, 4))
        plt.bar(names, vals)
        plt.xticks(rotation=rotation, ha="right", fontsize=7)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.grid(True, axis="y", alpha=0.3)
        save(fname)

    # 1. Task (end-to-end) latency, mean over reps.
    bar(names, [summary[n]["mean_latency"] for n in names],
        "mean latency (model ticks)", "Task latency by scenario",
        "r1_latency.png")
    # 2. p99 latency.
    bar(names, [summary[n]["mean_p99"] for n in names],
        "p99 latency (model ticks)", "p99 latency by scenario",
        "r2_p99.png")
    # 3. Jitter (acquisition period std).
    bar(names, [summary[n]["mean_jitter"] for n in names],
        "period jitter (ticks std)", "Jitter by scenario",
        "r3_jitter.png")
    # 4. Deadline miss rate.
    bar(names, [100 * summary[n]["miss_rate"] for n in names],
        "deadline miss rate (%)", "Deadline miss rate by scenario",
        "r4_miss_rate.png")
    # 5. Max queue depth.
    bar(names, [summary[n]["mean_max_qdepth"] for n in names],
        "max queue depth (items)", "Queue depth by scenario",
        "r5_queue_depth.png")
    # 6. Context switches.
    bar(names, [summary[n]["mean_ctx"] for n in names],
        "context switches", "Context switches by scenario",
        "r6_ctx_switches.png")

    # 7. Processing load vs deadline behavior (twin axes).
    load = [n for n in names if n.startswith("load/")]
    load = sorted(load, key=lambda n: int(n.split("-")[1]))
    x = [int(n.split("-")[1]) for n in load]
    lat = [summary[n]["mean_latency"] for n in load]
    miss = [100 * summary[n]["miss_rate"] for n in load]
    fig, ax1 = plt.subplots()
    ax1.plot(x, lat, marker="o", label="mean latency")
    ax1.set_xlabel("processing ticks/item (modeled)")
    ax1.set_ylabel("mean latency (ticks)")
    ax2 = ax1.twinx()
    ax2.plot(x, miss, marker="x", color="red", label="miss rate")
    ax2.set_ylabel("miss rate (%)")
    plt.title("Processing load vs deadline behavior (deadline=9 ticks)")
    fig.tight_layout()
    p = outdir / "r7_load_vs_deadline.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"wrote {p}")

    print(f"plots from {args.input} -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
