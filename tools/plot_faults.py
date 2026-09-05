#!/usr/bin/env python3
"""Plot Phase-5 fault-injection results from the real benchmark JSON.

Reads results/fault_injection.json and writes 7 PNGs to results/plots/.
Fails loudly if the JSON is missing or has no runs. All values are
measured/derived from the virtual SoC timing model (see docs/fault-injection.md).
"""
from __future__ import annotations

import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "results" / "fault_injection.json"
DEFAULT_OUT = ROOT / "results" / "plots"


def _load(path: pathlib.Path) -> dict:
    data = json.loads(path.read_text())
    runs = data.get("runs", [])
    if not runs:
        raise SystemExit(f"plot_faults: no runs in {path}")
    return data


def _mean(vals):
    return sum(vals) / len(vals) if vals else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot Phase-5 fault results.")
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    data = _load(pathlib.Path(args.input))
    summary: dict = data["summary"]
    faults = list(summary.keys())
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    def save(name):
        p = outdir / name
        plt.tight_layout()
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"wrote {p}")

    det = [summary[f]["detection_latency"]["mean"] for f in faults]
    rec = [summary[f]["recovery_latency"]["mean"] for f in faults]

    # 1. Detection latency by fault (measured, model ticks).
    plt.figure(figsize=(10, 4))
    plt.bar(faults, det)
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("detection latency (model ticks, measured mean)")
    plt.title("Fault detection latency by fault")
    plt.grid(True, axis="y", alpha=0.3)
    save("f1_detection_latency.png")

    # 2. Recovery latency by fault (measured, model ticks).
    plt.figure(figsize=(10, 4))
    plt.bar(faults, rec)
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("recovery latency (model ticks, measured mean)")
    plt.title("Fault recovery latency by fault")
    plt.grid(True, axis="y", alpha=0.3)
    save("f2_recovery_latency.png")

    # 3. Detection vs recovery latency (derived scatter).
    plt.figure()
    for f, d, r in zip(faults, det, rec):
        plt.scatter([d], [r])
        plt.annotate(f, (d, r), fontsize=7)
    plt.xlabel("detection latency (ticks)")
    plt.ylabel("recovery latency (ticks)")
    plt.title("Detection vs recovery latency")
    plt.grid(True, alpha=0.3)
    save("f3_detection_vs_recovery.png")

    # 4. IRQ count by fault (measured total across reps).
    plt.figure(figsize=(10, 4))
    plt.bar(faults, [summary[f]["irq_total"] for f in faults])
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("IRQ count total (measured)")
    plt.title("IRQ count by fault")
    plt.grid(True, axis="y", alpha=0.3)
    save("f4_irq_by_fault.png")

    # 5. Final-state distribution (measured counts).
    states = sorted({s for f in faults for s in summary[f]["final_states"]})
    bottom = [0] * len(faults)
    plt.figure(figsize=(10, 4))
    for s in states:
        vals = [summary[f]["final_states"].get(s, 0) for f in faults]
        plt.bar(faults, vals, bottom=bottom, label=s)
        bottom = [b + v for b, v in zip(bottom, vals)]
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("runs (measured)")
    plt.title("Final-state distribution by fault")
    plt.legend()
    plt.grid(True, axis="y", alpha=0.3)
    save("f5_final_states.png")

    # 6. DMA fault outcomes (grouped detection/recovery, measured means).
    dma_faults = [f for f in faults if f.startswith("dma-")]
    x = range(len(dma_faults))
    w = 0.35
    plt.figure()
    plt.bar([i - w / 2 for i in x],
            [summary[f]["detection_latency"]["mean"] for f in dma_faults],
            width=w, label="detection")
    plt.bar([i + w / 2 for i in x],
            [summary[f]["recovery_latency"]["mean"] for f in dma_faults],
            width=w, label="recovery")
    plt.xticks(list(x), dma_faults, rotation=20, ha="right")
    plt.ylabel("ticks (measured mean)")
    plt.title("DMA fault outcomes")
    plt.legend()
    plt.grid(True, axis="y", alpha=0.3)
    save("f6_dma_outcomes.png")

    # 7. Interrupt-storm behavior (detection latency + IRQ totals).
    storm = [f for f in faults if f.startswith("irq-storm")]
    x = range(len(storm))
    w = 0.35
    fig, ax1 = plt.subplots()
    ax1.bar([i - w / 2 for i in x],
            [summary[f]["detection_latency"]["mean"] for f in storm],
            width=w, label="detection ticks")
    ax1.set_ylabel("detection latency (ticks)")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(storm, rotation=20, ha="right")
    ax2 = ax1.twinx()
    ax2.bar([i + w / 2 for i in x],
            [summary[f]["irq_total"] for f in storm],
            width=w, color="orange", label="IRQ total")
    ax2.set_ylabel("IRQ total (measured)")
    plt.title("Interrupt-storm behavior")
    fig.tight_layout()
    p = outdir / "f7_storm_behavior.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"wrote {p}")

    print(f"plots from {args.input} -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
