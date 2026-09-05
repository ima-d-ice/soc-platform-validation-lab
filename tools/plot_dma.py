#!/usr/bin/env python3
"""Plot Phase-4 DMA results from the real benchmark JSON (no placeholder data).

Reads results/cpu_vs_dma_phase4.json (rep 0) and writes 8 PNGs to
results/plots/. Fails loudly if the JSON is missing or has no runs.
All values are measured/derived from the virtual SoC timing model.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "results" / "cpu_vs_dma_phase4.json"
DEFAULT_OUT = ROOT / "results" / "plots"


def _load(path: pathlib.Path) -> dict:
    data = json.loads(path.read_text())
    runs = [r for r in data.get("runs", []) if r.get("rep", 0) == 0]
    if not runs:
        raise SystemExit(f"plot_dma: no rep-0 runs in {path}")
    return {"params": data.get("params", {}), "runs": runs}


def _sel(runs, *, burst=None, mode=None):
    out = runs
    if burst is not None:
        out = [r for r in out if r["burst"] == burst]
    if mode is not None:
        out = [r for r in out if r["completion_mode"] == mode]
    return sorted(out, key=lambda r: r["transfer_size"])


def _sizes(runs):
    return sorted({r["transfer_size"] for r in runs})


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot Phase-4 DMA results.")
    ap.add_argument("--inp", default=str(DEFAULT_IN))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    bundle = _load(pathlib.Path(args.inp))
    runs = bundle["runs"]
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sizes = _sizes(runs)
    bursts = sorted({r["burst"] for r in runs})

    def save(name):
        p = outdir / name
        plt.tight_layout()
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"wrote {p}")

    # 1. DMA throughput vs transfer size for each burst (irq).
    plt.figure()
    for b in bursts:
        rows = _sel(runs, burst=b, mode="irq")
        plt.plot([r["transfer_size"] for r in rows],
                 [r["throughput"] for r in rows], marker="o", label=f"burst={b}")
    plt.xscale("log", base=2)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("DMA bytes/tick (measured+derived, virtual model)")
    plt.title("DMA throughput vs transfer size (irq completion)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("01_throughput_vs_size.png")

    # 2. DMA ticks vs transfer size for each burst (irq).
    plt.figure()
    for b in bursts:
        rows = _sel(runs, burst=b, mode="irq")
        plt.plot([r["transfer_size"] for r in rows],
                 [r["total_ticks"] for r in rows], marker="o", label=f"burst={b}")
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("DMA total ticks (measured, log10)")
    plt.title("DMA ticks vs transfer size (irq completion)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("02_ticks_vs_size.png")

    # 3. Speedup vs transfer size (irq per burst + polling burst=4 dashed).
    plt.figure()
    for b in bursts:
        rows = _sel(runs, burst=b, mode="irq")
        plt.plot([r["transfer_size"] for r in rows],
                 [r["speedup_vs_cpu"] for r in rows], marker="o", label=f"irq burst={b}")
    mid = bursts[len(bursts) // 2] if bursts else 4
    rows = _sel(runs, burst=mid, mode="polling")
    if rows:
        plt.plot([r["transfer_size"] for r in rows],
                 [r["speedup_vs_cpu"] for r in rows], marker="x",
                 linestyle="--", label=f"polling burst={mid}")
    plt.xscale("log", base=2)
    plt.axhline(1.0, color="k", linewidth=1)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("speedup vs CPU ticks (derived)")
    plt.title("Speedup vs transfer size")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("03_speedup_vs_size.png")

    # 4. Throughput vs burst size (one line per transfer size, irq).
    plt.figure()
    for s in sizes:
        rows = sorted([r for r in runs if r["transfer_size"] == s
                       and r["completion_mode"] == "irq"], key=lambda r: r["burst"])
        plt.plot([r["burst"] for r in rows],
                 [r["throughput"] for r in rows], marker="o", label=f"{s}B")
    plt.xscale("log", base=2)
    plt.xlabel("burst (words, log2)")
    plt.ylabel("DMA bytes/tick (derived)")
    plt.title("Throughput vs burst size (irq completion)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("04_throughput_vs_burst.png")

    # 5. CPU vs DMA total ticks (cpu line + dma burst=4 irq).
    plt.figure()
    rows = _sel(runs, burst=4, mode="irq")
    if not rows:
        rows = _sel(runs, mode="irq")[: len(sizes)]
    plt.plot([r["transfer_size"] for r in rows],
             [r["cpu_ticks"] for r in rows], marker="o", label="CPU copy")
    plt.plot([r["transfer_size"] for r in rows],
             [r["total_ticks"] for r in rows], marker="s", label="DMA total (burst=4, irq)")
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("ticks (measured, log10)")
    plt.title("CPU vs DMA total ticks")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("05_cpu_vs_dma_ticks.png")

    # 6. DMA polling vs IRQ total ticks (burst=4).
    plt.figure()
    for m in ("polling", "irq"):
        rows = _sel(runs, burst=4, mode=m)
        plt.plot([r["transfer_size"] for r in rows],
                 [r["total_ticks"] for r in rows], marker="o", label=m)
    plt.xscale("log", base=2)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("DMA total ticks (measured)")
    plt.title("DMA polling vs IRQ total ticks (burst=4)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("06_polling_vs_irq_ticks.png")

    # 7. CPU work vs transfer size (bus ops, measured).
    plt.figure()
    rows = _sel(runs, burst=4, mode="irq")
    plt.plot([r["transfer_size"] for r in rows],
             [r["cpu_work"]["cpu_path_bus_ops"] for r in rows],
             marker="o", label="CPU path bus ops")
    plt.plot([r["transfer_size"] for r in rows],
             [r["cpu_work"]["dma_path_bus_ops"] for r in rows],
             marker="s", label="DMA path bus ops (burst=4, irq)")
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("bus ops (measured MEM_ACC delta, log10)")
    plt.title("CPU work vs transfer size")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("07_cpu_work_vs_size.png")

    # 8. DMA bytes/tick vs burst size (transfer-only throughput, irq).
    plt.figure()
    for s in sizes:
        rows = sorted([r for r in runs if r["transfer_size"] == s
                       and r["completion_mode"] == "irq"], key=lambda r: r["burst"])
        plt.plot([r["burst"] for r in rows],
                 [r["transfer_throughput"] for r in rows], marker="o", label=f"{s}B")
    plt.xscale("log", base=2)
    plt.xlabel("burst (words, log2)")
    plt.ylabel("transfer bytes/tick (derived)")
    plt.title("DMA transfer throughput vs burst size (irq)")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("08_transfer_throughput_vs_burst.png")

    print(f"plots from {args.inp} -> {outdir} (rep 0, n={len(runs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
