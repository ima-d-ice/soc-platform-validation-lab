#!/usr/bin/env python3
"""Final plots (Phase 8): 8 PNGs sourced ONLY from results/final_matrix.json.

Fails loudly if the JSON or any required experiment is missing. All values
are measured/derived from the virtual SoC model ticks.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "results" / "final_matrix.json"
DEFAULT_OUT = ROOT / "results" / "plots"


def main() -> int:
    ap = argparse.ArgumentParser(description="Final system plots.")
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.input).read_text())
    exps = data["experiments"]
    for need in ("F1-cpu-vs-dma", "F2-burst-scaling", "F3-polling-vs-irq",
                 "F4-buffering", "F5-rtos-priority", "F6-linux",
                 "F7-faults", "F8-stress"):
        if need not in exps or not exps[need]:
            raise SystemExit(f"final_plots: missing experiment {need}")
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    r0 = lambda rows: [r for r in rows if r.get("rep", 0) == 0]  # noqa: E731

    def save(name):
        p = outdir / name
        plt.tight_layout()
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"wrote {p}")

    f1, f2 = r0(exps["F1-cpu-vs-dma"]), r0(exps["F2-burst-scaling"])
    sizes = sorted({r["transfer_size"] for r in f1})

    # 1. Latency comparison: cpu vs dma-irq single transfers.
    # (Linux e2e and RTOS latencies have different semantics — compared
    # separately in m2 with an explicit warning, never merged here.)
    f6 = r0(exps["F6-linux"])
    plt.figure()
    cpu = [next(r["cpu_ticks"] for r in f1 if r["transfer_size"] == s
                and r["completion_mode"] == "irq") for s in sizes]
    dma = [next(r["total_ticks"] for r in f1 if r["transfer_size"] == s
                and r["completion_mode"] == "irq") for s in sizes]
    plt.plot(sizes, cpu, marker="o", label="CPU copy total")
    plt.plot(sizes, dma, marker="s", label="DMA total (burst4, irq)")
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("ticks (log10)")
    plt.title("Latency comparison")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("m1_latency_comparison.png")

    # 2. p99 comparison across modes (dma latencies + linux e2e + rtos).
    f5 = r0(exps["F5-rtos-priority"])
    plt.figure()
    labels = ["DMA 4KB", "Linux 4KB", "RTOS prio-H", "RTOS prio-L"]
    p99 = [
        next(r["transfer_ticks"] for r in f2 if r["transfer_size"] == 4096
             and r["burst"] == 4),
        next(r["e2e_stats"]["p99"] for r in f6 if r["transfer_size"] == 4096
             and r["buffers"] == 4 and r["completion"] == "irq"),
        next(r["latency_stats"]["p99"] for r in f5
             if r["priority"] == "proc5-tele2"),
        next(r["latency_stats"]["p99"] for r in f5
             if r["priority"] == "proc2-tele5"),
    ]
    plt.bar(labels, p99)
    plt.xticks(rotation=15, ha="right")
    plt.ylabel("p99 ticks (mixed semantics — see report)")
    plt.title("p99 comparison (per-mode definitions differ)")
    plt.grid(True, axis="y", alpha=0.3)
    save("m2_p99_comparison.png")

    # 3. Throughput comparison.
    plt.figure()
    thr_dma = [next(r["throughput"] for r in f1 if r["transfer_size"] == s
                    and r["completion_mode"] == "irq") for s in sizes]
    thr_lin = [next(r["throughput"] for r in f6 if r["transfer_size"] == s
                    and r["buffers"] == 4 and r["completion"] == "irq")
               for s in sizes]
    plt.plot(sizes, thr_dma, marker="o", label="DMA")
    plt.plot(sizes, thr_lin, marker="s", label="Linux path (buf4)")
    plt.xscale("log", base=2)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("bytes/tick (derived)")
    plt.title("Throughput comparison")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("m3_throughput_comparison.png")

    # 4. DMA scaling (burst lines from F2).
    plt.figure()
    for b in (1, 4, 16):
        rows = sorted([r for r in f2 if r["burst"] == b],
                      key=lambda r: r["transfer_size"])
        plt.plot([r["transfer_size"] for r in rows],
                 [r["transfer_ticks"] for r in rows],
                 marker="o", label=f"burst={b}")
    plt.xscale("log", base=2)
    plt.yscale("log", base=10)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("transfer ticks (log10)")
    plt.title("DMA scaling")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("m4_dma_scaling.png")

    # 5. Interrupt behavior (F3 mem deltas + F8 storm rate).
    f3 = exps["F3-polling-vs-irq"]
    plt.figure()
    x = [r["transfer_size"] for r in f3]
    plt.plot(x, [r["poll_mem"] for r in f3], marker="o",
             label="polling MEM_ACC")
    plt.plot(x, [r["irq_mem"] for r in f3], marker="s",
             label="irq MEM_ACC")
    plt.xscale("log", base=2)
    plt.xlabel("transfer size (bytes, log2)")
    plt.ylabel("bus accesses (measured)")
    plt.title("Interrupt behavior: completion-path bus cost")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    save("m5_interrupt_behavior.png")

    # 6. RTOS scheduling (F5 mean latency + starvation annotation).
    plt.figure()
    labels = [r["priority"] for r in f5]
    plt.bar(labels,
            [r["latency_stats"]["mean"] for r in f5])
    plt.ylabel("mean latency (ticks)")
    plt.title("RTOS scheduling: priority impact "
              f"(starved: {[sorted(r['starvation_events']) for r in f5]})")
    plt.grid(True, axis="y", alpha=0.3)
    save("m6_rtos_scheduling.png")

    # 7. Fault detection/recovery (F7 means).
    f7 = r0(exps["F7-faults"])
    names = [r["fault"] for r in f7]
    x = range(len(names))
    w = 0.35
    plt.figure()
    plt.bar([i - w / 2 for i in x],
            [r["detection_latency_ticks"] for r in f7], width=w,
            label="detection")
    plt.bar([i + w / 2 for i in x],
            [r["recovery_latency_ticks"] for r in f7], width=w,
            label="recovery")
    plt.xticks(list(x), names, rotation=20, ha="right")
    plt.ylabel("ticks (measured)")
    plt.title("Fault detection/recovery")
    plt.legend()
    plt.grid(True, axis="y", alpha=0.3)
    save("m7_faults.png")

    # 8. Stress/limit behavior (F8 selected counters).
    f8 = r0(exps["F8-stress"])
    by_name = {r["scenario"]: r for r in f8}
    plt.figure()
    labels = ["storm-irqs/50", "dma-KB/tick*1000", "drops", "resets OK",
              "timeouts", "rejected/4"]
    storm = by_name["high-irq-rate"]["irqs_handled"] / 5
    vals = [storm,
            by_name["dma-pressure"]["sustained_bytes_per_tick"] * 1000,
            by_name["queue-pressure"]["drops"],
            by_name["repeated-reset"]["recovered"],
            by_name["comm-timeout"]["timeouts"],
            by_name["invalid-access"]["rejected"] / 4]
    plt.bar(labels, vals)
    plt.xticks(rotation=20, ha="right", fontsize=7)
    plt.yscale("log", base=10)
    plt.ylabel("scaled counts, log10 (see labels)")
    plt.title("Stress/limit behavior (scales differ — read labels)")
    plt.grid(True, axis="y", alpha=0.3)
    save("m8_stress.png")

    print(f"plots from {args.input} -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
