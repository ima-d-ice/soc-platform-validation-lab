#!/usr/bin/env python3
"""Plot Phase-7 Linux platform results from the real benchmark JSON.

Reads results/linux_platform.json and writes 6 PNGs to results/plots/.
Fails loudly on missing data. Values are measured/derived from the
virtual SoC + userspace driver model ticks (see docs/linux-platform.md).
"""
from __future__ import annotations

import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "results" / "linux_platform.json"
DEFAULT_OUT = ROOT / "results" / "plots"


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot Phase-7 Linux results.")
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.input).read_text())
    runs = [r for r in data.get("runs", []) if r.get("rep", 0) == 0]
    if not runs:
        raise SystemExit(f"plot_linux: no rep-0 runs in {args.input}")
    sizes = sorted({r["transfer_size"] for r in runs})
    depths = sorted({r["buffers"] for r in runs})
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    def cell(size, depth, mode):
        return next(r for r in runs if r["transfer_size"] == size
                    and r["buffers"] == depth and r["completion"] == mode)

    def save(name):
        p = outdir / name
        plt.tight_layout()
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"wrote {p}")

    # 1. Latency vs transfer size (mean e2e, irq, one line per depth).
    plt.figure()
    for d in depths:
        plt.plot(sizes, [cell(s, d, "irq")["completion_ticks"] for s in sizes],
                 marker="o", label=f"bufs={d}")
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("mean e2e ticks (log10)")
    plt.title("Latency vs transfer size (irq)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("l1_latency_vs_size.png")

    # 2. Throughput vs transfer size (irq per depth).
    plt.figure()
    for d in depths:
        plt.plot(sizes, [cell(s, d, "irq")["throughput"] for s in sizes],
                 marker="o", label=f"bufs={d}")
    plt.xscale("log", base=2)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("throughput (bytes/tick, derived)")
    plt.title("Throughput vs transfer size (irq)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("l2_throughput_vs_size.png")

    # 3. Polling vs notification (mean e2e, depth=4).
    plt.figure()
    for m in ("polling", "irq"):
        plt.plot(sizes, [cell(s, 4, m)["completion_ticks"] for s in sizes],
                 marker="o", label=m)
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("mean e2e ticks (log10)")
    plt.title("Polling vs notification (4 buffers)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("l3_polling_vs_notification.png")

    # 4. Buffer size vs latency (mean e2e per size across depths).
    plt.figure()
    for s in sizes:
        plt.plot(depths, [cell(s, d, "irq")["completion_ticks"] for d in depths],
                 marker="o", label=f"{s}B")
    plt.xlabel("buffer count (ring depth)")
    plt.ylabel("mean e2e ticks")
    plt.title("Buffer size vs latency (irq)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    save("l4_buffers_vs_latency.png")

    # 5. Queue depth (high-water outstanding per size/depth, irq).
    plt.figure()
    for s in sizes:
        plt.plot(depths, [cell(s, d, "irq")["queue_depth"] for d in depths],
                 marker="o", label=f"{s}B")
    plt.xlabel("buffer count (ring depth)")
    plt.ylabel("max outstanding frames (measured)")
    plt.title("Queue depth")
    plt.legend()
    plt.grid(True, alpha=0.3)
    save("l5_queue_depth.png")

    # 6. Dropped-buffer behavior (refused submits per size/depth, irq).
    plt.figure()
    for s in sizes:
        plt.plot(depths, [cell(s, d, "irq")["drops"] for d in depths],
                 marker="o", label=f"{s}B")
    plt.xlabel("buffer count (ring depth)")
    plt.ylabel("refused submits (measured backpressure)")
    plt.title("Dropped-buffer behavior")
    plt.legend()
    plt.grid(True, alpha=0.3)
    save("l6_drops.png")

    print(f"plots from {args.input} -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
