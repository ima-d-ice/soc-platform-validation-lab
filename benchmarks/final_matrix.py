#!/usr/bin/env python3
"""Final system matrix (Phase 8): EXP-F1..F8 in one deterministic run.

Every experiment reuses the phase benchmark definitions by importing them
— no benchmark is redefined here, so cross-phase numbers stay comparable:
  F1/F2/F3 <- benchmarks.cpu_vs_dma.run_cell
  F4/F6    <- benchmarks.linux_platform.run_cell
  F5       <- benchmarks.rtos_scheduling.run_pipeline
  F7       <- benchmarks.fault_injection.CASES
  F8       <- new controlled stress scenarios on the same primitives
Fresh model state per cell. Model ticks throughout; statistics derived;
workloads modeled. See docs/final-system.md (generated report prose) and
docs/limitations.md.

Usage:
  python3 benchmarks/final_matrix.py \
    --config configs/base.yaml \
    --sizes 64,1024,4096,16384 \
    --reps 3 \
    --out results/final_matrix.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks.cpu_vs_dma import run_cell as dma_cell
from benchmarks.fault_injection import CASES as FAULT_CASES
from benchmarks.linux_platform import run_cell as linux_cell
from benchmarks.rtos_scheduling import run_pipeline as rtos_run
from linux.driver import StreamDriver, StreamError
from soc.bus import BusError
from soc.faults import Fault, FaultInjector
from soc.soc import SoC, load_config

SIZES_DEFAULT = (64, 1024, 4096, 16384)
F7_FAULTS = ["dma-timeout", "uart-stuck", "irq-storm-mixed",
             "mmio-unmapped-read"]


def _pct(vals, p):
    s = sorted(vals)
    if not s:
        return 0
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s) + 0.5)) - 1))
    return s[k]


def _lat_stats(vals):
    s = sorted(vals)
    n = len(s)
    if not n:
        return {"n": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0, "mean": 0,
                "jitter": 0}
    return {"n": n, "p50": _pct(s, 50), "p95": _pct(s, 95), "p99": _pct(s, 99),
            "max": s[-1], "mean": sum(s) / n,
            "jitter": statistics.pstdev(s) if n > 1 else 0}


# -- F8 stress scenarios (fresh SoC each; deterministic) --
def stress_high_irq_rate(config):
    soc = SoC(config)
    soc.boot()
    soc.write(0x20003000, 1 << 1)
    soc.write(0x20001004, 2)
    soc.write(0x20001000, 0x1 | 0x2 | 0x4)
    handled = 0
    for _ in range(500):
        soc.step(1)
        if soc.read(0x20003004) & (1 << 1):
            assert soc.read(0x20003008) == 1
            soc.write(0x2000300C, 1)
            soc.write(0x20001010, 0x1)
            handled += 1
    return {"ticks": 500, "irqs_handled": handled,  # measured
            "rate_per_100_ticks": handled / 5}  # derived


def stress_dma_pressure(config, size=16384, count=8):
    soc = SoC(config)
    soc.boot()
    for i in range(size // 4):
        soc.sram_write_word(0x10000000 + i * 4, 0xA0000000 | i)
    t0, moved = soc.ticks, 0
    for k in range(count):
        dst = 0x10004000 + (k % 2) * 0x4000
        soc.write(0x20002000, 0x10000000)
        soc.write(0x20002004, dst)
        soc.write(0x20002008, size)
        soc.write(0x2000200C, 0x1)
        soc.run_until(lambda: soc.read(0x20002010) & 0x6, max_ticks=100000)
        assert soc.read(0x20002010) & 0x2
        soc.write(0x20002014, 1)
        moved += size
    total = soc.ticks - t0
    return {"transfers": count, "bytes": moved, "total_ticks": total,  # measured
            "sustained_bytes_per_tick": moved / total}  # derived


def stress_queue_pressure(config):
    r = rtos_run(config, period=5, acq=0, proc=6, telem=2, qdepth=1,
                 deadline=100, max_items=40, run_ticks=6000)
    return {"drops": r["drops"], "completions": r["completions"],  # measured
            "miss_rate": r["miss_rate"],  # derived
            "max_qdepth": r["max_queue_depth"]}  # measured


def stress_task_starvation(config):
    r = rtos_run(config, period=5, acq=0, proc=20, telem=2, qdepth=4,
                 proc_prio=5, telem_prio=1, deadline=200, max_items=30,
                 run_ticks=4000)
    return {"starved_tasks": sorted(r["starvation_events"]),  # measured gaps
            "tele_runs": r["run_counts"].get("tele", 0),  # measured
            "proc_runs": r["run_counts"].get("proc", 0)}  # measured


def stress_comm_timeout(config):
    soc = SoC(config)
    soc.boot()
    drv = StreamDriver(soc, ring_depth=2)
    drv.init(irq_mode=False)
    h = drv.alloc(64)
    inj = FaultInjector(soc)
    t = drv.submit(h, 64, 0x77, timeout=100)
    inj.inject(Fault("dma-timeout"))
    timeouts = 0
    for _ in range(3):
        try:
            drv.wait(t, timeout=50)
        except StreamError:
            timeouts += 1
            drv.abort()  # engine recovery (also unlatches: reset clears it)
            inj.inject(Fault("dma-timeout"))  # stuck source persists
            t = drv.submit(h, 64, 0x77, timeout=100)
    inj.clear("dma-timeout")
    drv.abort()
    return {"rounds": 3, "timeouts": timeouts,  # measured
            "engine_idle_after_abort": soc.read(0x20002010) == 0}  # measured


def stress_invalid_access(config, n=20):
    soc = SoC(config)
    soc.boot()
    rejected = 0
    for i in range(n):
        try:
            soc.read(0x30000000 + (i % 4) * 4)
        except BusError:
            rejected += 1
    return {"attempts": n, "rejected": rejected,  # measured
            "stalls": soc.read(0x20004010)}  # measured


def stress_repeated_reset(config, rounds=5):
    soc = SoC(config)
    soc.boot()
    recovered = 0
    for _ in range(rounds):
        soc.write(0x20002000, 0x10000000)
        soc.write(0x20002004, 0x10004000)
        soc.write(0x20002008, 1024)
        soc.write(0x2000200C, 0x1)
        soc.step(100)  # mid-transfer
        soc.reset_peripherals()
        assert soc.read(0x20002010) == 0
        soc.write(0x20002000, 0x10000000)
        soc.write(0x20002004, 0x10004000)
        soc.write(0x20002008, 1024)
        soc.write(0x2000200C, 0x1)
        soc.run_until(lambda: soc.read(0x20002010) & 0x2, max_ticks=5000)
        soc.write(0x20002014, 1)
        recovered += 1
    return {"rounds": rounds, "recovered": recovered}  # measured


STRESS = {
    "high-irq-rate": stress_high_irq_rate,
    "dma-pressure": stress_dma_pressure,
    "queue-pressure": stress_queue_pressure,
    "task-starvation": stress_task_starvation,
    "comm-timeout": stress_comm_timeout,
    "invalid-access": stress_invalid_access,
    "repeated-reset": stress_repeated_reset,
}


def _dominant(breakdown):
    total = sum(breakdown.values()) or 1
    name = max(breakdown, key=breakdown.get)
    return {"factor": name, "share": breakdown[name] / total,
            "breakdown": breakdown}


def main() -> int:
    ap = argparse.ArgumentParser(description="Final system matrix (measured).")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--sizes", default=",".join(map(str, SIZES_DEFAULT)))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results" / "final_matrix.json"))
    args = ap.parse_args()
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")

    config = load_config(args.config)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    exps: dict = {}

    # F1: CPU vs DMA scaling (burst 4, both completions).
    f1 = []
    for rep in range(args.reps):
        for s in sizes:
            for mode in ("polling", "irq"):
                r = dma_cell(config, s, 4, mode)
                r["rep"] = rep
                f1.append(r)
    exps["F1-cpu-vs-dma"] = f1

    # F2: DMA burst scaling (bursts 1/4/16, irq).
    f2 = []
    for rep in range(args.reps):
        for s in sizes:
            for b in (1, 4, 16):
                cfg = dict(config, dma_burst=b)
                soc = SoC(cfg)
                soc.boot()
                from benchmarks.cpu_vs_dma import measure_dma_irq, SRAM_BASE, DMA_DST
                m = measure_dma_irq(soc, SRAM_BASE, DMA_DST, s)
                m.update({"transfer_size": s, "burst": b, "rep": rep})
                f2.append(m)
    exps["F2-burst-scaling"] = f2

    # F3: polling vs IRQ (derived view over F1 rows, no rerun).
    f3 = []
    for s in sizes:
        prows = [r for r in f1 if r["transfer_size"] == s
                 and r["completion_mode"] == "polling" and r["rep"] == 0]
        irows = [r for r in f1 if r["transfer_size"] == s
                 and r["completion_mode"] == "irq" and r["rep"] == 0]
        p, i = prows[0], irows[0]
        f3.append({"transfer_size": s,
                   "poll_ticks": p["total_ticks"], "irq_ticks": i["total_ticks"],
                   "poll_mem": p["mem_accesses"], "irq_mem": i["mem_accesses"],
                   "poll_irq": p["irq_count"], "irq_irq": i["irq_count"]})
    exps["F3-polling-vs-irq"] = f3

    # F4: buffering impact (linux depths 1/4/8, sizes small+large, irq).
    f4 = []
    for rep in range(args.reps):
        for s in (sizes[0], sizes[-1]):
            for d in (1, 4, 8):
                r = linux_cell(config, s, d, "irq")
                r["rep"] = rep
                f4.append(r)
    exps["F4-buffering"] = f4

    # F5: RTOS priority impact (identical overload, swapped priorities).
    f5 = []
    for rep in range(args.reps):
        for prio in ({"proc_prio": 5, "telem_prio": 2},
                     {"proc_prio": 2, "telem_prio": 5}):
            r = rtos_run(config, period=10, acq=1, proc=9, telem=5,
                         qdepth=4, deadline=200, max_items=30,
                         run_ticks=6000, **prio)
            r["rep"] = rep
            r["priority"] = f"proc{prio['proc_prio']}-tele{prio['telem_prio']}"
            f5.append(r)
    exps["F5-rtos-priority"] = f5

    # F6: Linux buffer/notification behavior (sizes x modes, depth 4).
    f6 = []
    for rep in range(args.reps):
        for s in sizes:
            for m in ("polling", "irq"):
                r = linux_cell(config, s, 4, m)
                r["rep"] = rep
                f6.append(r)
    exps["F6-linux"] = f6

    # F7: fault detection/recovery (subset of fault matrix).
    f7 = []
    for rep in range(args.reps):
        for name in F7_FAULTS:
            soc = SoC(config)
            soc.boot()
            inj = FaultInjector(soc)
            from benchmarks import fault_injection as fi
            row = fi.CASES[name](soc, inj, rep)
            f7.append(row)
    exps["F7-faults"] = f7

    # F8: stress/limit behavior.
    f8 = []
    for rep in range(args.reps):
        for name, fn in STRESS.items():
            row = {"scenario": name, "rep": rep}
            row.update(fn(config))
            f8.append(row)
    exps["F8-stress"] = f8

    # Bottlenecks: dominant measured share per workload (derived rule:
    # largest share of the decomposed tick budget wins).
    bottlenecks = {}
    for s in sizes:
        prows = [r for r in f1 if r["transfer_size"] == s
                 and r["completion_mode"] == "irq" and r["rep"] == 0]
        r = prows[0]
        bottlenecks[f"dma-{s}B"] = _dominant({
            "transfer": r["dma_transfer_ticks"],
            "setup_ack": r["total_ticks"] - r["dma_transfer_ticks"]})
    for row in [x for x in f8 if x["rep"] == 0]:
        if row["scenario"] == "queue-pressure":
            bottlenecks["queue-pressure"] = _dominant(
                {"drops": row["drops"], "completions": row["completions"]})

    payload = {
        "params": {
            "config": pathlib.Path(args.config).name,
            "sizes": sizes, "repetitions": args.reps,
            "reuses_definitions_from": [
                "benchmarks.cpu_vs_dma", "benchmarks.linux_platform",
                "benchmarks.rtos_scheduling", "benchmarks.fault_injection"],
            "note": "F1/F2/F4/F5/F6 call phase benchmark helpers directly; "
                    "F3 is a derived view over F1 rows; ticks measured, "
                    "stats derived, workloads modeled.",
        },
        "experiments": exps,
        "bottlenecks": bottlenecks,
        "provenance": {"measured": ["ticks", "counters", "latencies",
                                    "drops", "misses", "irqs", "states"],
                       "derived": ["p50", "p95", "p99", "throughput",
                                   "speedup", "bottleneck shares"],
                       "modeled": ["sizes", "bursts", "depths", "periods",
                                   "workloads", "budgets"]},
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"config: {payload['params']['config']} sizes={sizes} "
          f"reps={args.reps}")
    for exp, rows in exps.items():
        print(f"  {exp}: {len(rows)} rows")
    print("bottlenecks (derived dominant share):")
    for k, v in bottlenecks.items():
        print(f"  {k}: {v['factor']} ({v['share']:.2f})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
