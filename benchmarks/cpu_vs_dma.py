#!/usr/bin/env python3
"""CPU memcpy vs DMA benchmark, Phase 4: burst / size / completion study.

All timing comes from the virtual SoC timing model (soc.ticks + PERF
counters). Nothing is synthesised.

Method (deterministic):
- CPU path: word-by-word soc.read + soc.write loop. Each word costs
  1 execute tick + ram_latency_ticks wait ticks via soc.step() (config
  `ram_latency_ticks`; base = 2, so 3 ticks/word). MEM_ACC/STALLS/CYCLES
  come from the model itself.
- DMA polling path: program SRC/DST/LEN, START *without* IRQ_ENABLE, then
  poll STATUS until DONE. Poll reads are counted as completion cost.
  Expect IRQ_COUNT == 0.
- DMA IRQ path: program SRC/DST/LEN, START with IRQ_ENABLE, run until DONE,
  then ACK + DMA.IRQ_CLEAR + INTC.CLEAR. Expect IRQ_COUNT == 1.
  Transfer ticks follow the spec burst formula:
    words = LEN/4; bursts = ceil(words/burst)
    ticks = words*latency_per_word + (bursts-1)
  Burst size is config-only (no BURST register).
- Correctness: destination bytes are read back and compared on every run.
- Fresh SoC + boot() per measurement. ns derived from ticks via
  cpu_frequency_mhz (informational only).
- SRAM capacity: 64KB total; regions are SRC @+0x0000, CPU_DST @+0x4000,
  DMA_DST @+0x8000. Sizes above 16KB are refused with a clear error.

Provenance per run:
- measured: ticks/counters read from the model.
- derived: arithmetic on measured values (throughput, speedup, crossover).
- modeled: the CPU per-word wait assumption documented here.

Writes JSON to --out (default results/cpu_vs_dma_phase4.json, gitignored).
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soc.soc import SoC, load_config

SRAM_BASE = 0x10000000
SRAM_SIZE = 0x10000
CPU_DST = 0x10004000
DMA_DST = 0x10008000

DMA_BASE = 0x20002000
D_SRC = DMA_BASE + 0x00
D_DST = DMA_BASE + 0x04
D_LEN = DMA_BASE + 0x08
D_CTRL = DMA_BASE + 0x0C
D_STATUS = DMA_BASE + 0x10
D_IRQ_CLEAR = DMA_BASE + 0x14

INTC_BASE = 0x20003000
INTC_ENABLE = INTC_BASE + 0x00
INTC_PENDING = INTC_BASE + 0x04
INTC_ACK = INTC_BASE + 0x08
INTC_CLEAR = INTC_BASE + 0x0C

IRQ_DMA = 2
DONE = 1 << 1
ERROR = 1 << 2

DEFAULT_SIZES = (16, 64, 256, 1024, 4096, 16384)
DEFAULT_BURSTS = (1, 2, 4, 8, 16)
COMPLETIONS = ("polling", "irq")

MEASURED_FIELDS = [
    "cpu_ticks", "dma_transfer_ticks", "total_ticks", "dma_bytes",
    "mem_accesses", "irq_count", "stalls", "cpu_work_bus_ops",
    "completion_cost_reads",
]
DERIVED_FIELDS = [
    "throughput", "transfer_throughput", "speedup_vs_cpu",
    "cpu_work_avoided_bus_ops",
]
MODELED_FIELDS = ["cpu_per_word_ticks_note"]


def _pattern(nbytes: int) -> list[int]:
    nwords = nbytes // 4
    return [0xB1000000 | (i & 0xFFFFFF) for i in range(nwords)]


def _check_fit(nbytes: int) -> None:
    for base, name in ((SRAM_BASE, "SRC"), (CPU_DST, "CPU_DST"), (DMA_DST, "DMA_DST")):
        if base + nbytes > SRAM_BASE + SRAM_SIZE:
            raise ValueError(
                f"transfer size {nbytes}B at {name}=0x{base:08X} exceeds "
                f"64KB SRAM (top 0x{SRAM_BASE + SRAM_SIZE:08X}); "
                "64KB single transfers do not fit — capped at 16KB."
            )


def _snapshot(soc: SoC) -> dict:
    return {
        "ticks": soc.ticks,
        "cycles": soc.perf.cycles,
        "mem_acc": soc.perf.mem_acc,
        "irq": soc.perf.irq_count,
        "stalls": soc.perf.stalls,
        "dma_bytes": soc.perf.dma_bytes,
    }


def _delta(before: dict, after: dict) -> dict:
    return {k: after[k] - before[k] for k in before}


def measure_cpu(soc: SoC, src: int, dst: int, nbytes: int) -> dict:
    """Run word-by-word CPU memcpy on a booted SoC. Returns measurements."""
    assert nbytes % 4 == 0 and nbytes > 0
    _check_fit(nbytes)
    per_word = 1 + int(soc.config.get("ram_latency_ticks", 2))
    words = _pattern(nbytes)
    for i, w in enumerate(words):
        soc.sram_write_word(src + i * 4, w)
    before = _snapshot(soc)
    nwords = nbytes // 4
    for i in range(nwords):
        w = soc.read(src + i * 4)
        soc.write(dst + i * 4, w)
        soc.step(per_word)
    after = _snapshot(soc)
    got = [soc.sram_read_word(dst + i * 4) for i in range(nwords)]
    assert got == words, "CPU memcpy mismatch"
    d = _delta(before, after)
    ticks = d["ticks"]
    return {
        "nbytes": nbytes,
        "total_ticks": ticks,
        "cycles": d["cycles"],
        "mem_acc": d["mem_acc"],
        "irq": d["irq"],
        "stalls": d["stalls"],
        "bytes_per_tick": nbytes / ticks if ticks else 0.0,
    }


def _dma_program_and_start(soc: SoC, src: int, dst: int, nbytes: int, irq_en: bool) -> None:
    soc.write(D_SRC, src)
    soc.write(D_DST, dst)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1 | (0x2 if irq_en else 0))


def measure_dma_polling(soc: SoC, src: int, dst: int, nbytes: int,
                        max_ticks: int = 1000000) -> dict:
    """DMA with status-polling completion (no IRQ). Returns measurements."""
    assert nbytes % 4 == 0 and nbytes > 0
    _check_fit(nbytes)
    words = _pattern(nbytes)
    for i, w in enumerate(words):
        soc.sram_write_word(src + i * 4, w)
    soc.write(INTC_ENABLE, 0)  # polling: no lines enabled
    before = _snapshot(soc)
    _dma_program_and_start(soc, src, dst, nbytes, irq_en=False)
    poll_reads = 0
    transfer_ticks = 0
    while True:
        st = soc.read(D_STATUS)
        poll_reads += 1
        if st & (DONE | ERROR):
            break
        soc.step(1)
        transfer_ticks += 1
        if transfer_ticks >= max_ticks:
            raise TimeoutError("DMA polling timed out")
    assert soc.read(D_STATUS) & DONE, "DMA did not complete"
    assert soc.read(INTC_PENDING) == 0, "polling mode must not raise IRQ"
    soc.write(D_IRQ_CLEAR, 1)
    after = _snapshot(soc)
    nwords = nbytes // 4
    got = [soc.sram_read_word(dst + i * 4) for i in range(nwords)]
    assert got == words, "DMA polling mismatch"
    d = _delta(before, after)
    total = d["ticks"]
    return {
        "nbytes": nbytes,
        "mode": "polling",
        "total_ticks": total,
        "transfer_ticks": transfer_ticks,
        "setup_ack_ticks": total - transfer_ticks,
        "completion_cost_reads": poll_reads,
        "cycles": d["cycles"],
        "mem_acc": d["mem_acc"],
        "irq": d["irq"],
        "stalls": d["stalls"],
        "dma_bytes": d["dma_bytes"],
        "cpu_free_ticks": transfer_ticks,
        "bytes_per_tick": nbytes / total if total else 0.0,
        "transfer_bytes_per_tick": nbytes / transfer_ticks if transfer_ticks else 0.0,
    }


def measure_dma(soc: SoC, src: int, dst: int, nbytes: int) -> dict:
    """DMA with completion IRQ (legacy helper; kept for existing tests)."""
    return measure_dma_irq(soc, src, dst, nbytes)


def measure_dma_irq(soc: SoC, src: int, dst: int, nbytes: int,
                    max_ticks: int = 1000000) -> dict:
    """DMA with completion-IRQ path on a booted SoC. Returns measurements."""
    assert nbytes % 4 == 0 and nbytes > 0
    _check_fit(nbytes)
    words = _pattern(nbytes)
    for i, w in enumerate(words):
        soc.sram_write_word(src + i * 4, w)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    before = _snapshot(soc)
    _dma_program_and_start(soc, src, dst, nbytes, irq_en=True)
    transfer_ticks = soc.run_until(
        lambda: soc.read(D_STATUS) & (DONE | ERROR), max_ticks=max_ticks
    )
    assert soc.read(D_STATUS) & DONE, "DMA did not complete"
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    acked = soc.read(INTC_ACK)
    assert acked == IRQ_DMA
    # 3 explicit post-transfer completion reads above (STATUS check, PENDING
    # check, ACK); all also counted in the mem_acc delta. No estimate.
    completion_reads = 3
    soc.write(D_IRQ_CLEAR, 1)
    soc.write(INTC_CLEAR, IRQ_DMA)
    after = _snapshot(soc)
    nwords = nbytes // 4
    got = [soc.sram_read_word(dst + i * 4) for i in range(nwords)]
    assert got == words, "DMA mismatch"
    d = _delta(before, after)
    total = d["ticks"]
    return {
        "nbytes": nbytes,
        "mode": "irq",
        "total_ticks": total,
        "transfer_ticks": transfer_ticks,
        "setup_ack_ticks": total - transfer_ticks,
        "completion_cost_reads": completion_reads,
        "cycles": d["cycles"],
        "mem_acc": d["mem_acc"],
        "irq": d["irq"],
        "stalls": d["stalls"],
        "dma_bytes": d["dma_bytes"],
        "cpu_free_ticks": transfer_ticks,
        "bytes_per_tick": nbytes / total if total else 0.0,
        "transfer_bytes_per_tick": nbytes / transfer_ticks if transfer_ticks else 0.0,
    }


def _with_burst(config: dict, burst: int) -> dict:
    cfg = copy.deepcopy(config)
    cfg["dma_burst"] = burst
    return cfg


def run_cell(config: dict, nbytes: int, burst: int, completion: str) -> dict:
    """One (size, burst, mode) cell with fresh SoCs for CPU and DMA."""
    mhz = config.get("cpu_frequency_mhz", 100)
    cfg = _with_burst(config, burst)
    soc_cpu = SoC(config)  # CPU path is burst-independent; use base config
    soc_cpu.boot()
    cpu = measure_cpu(soc_cpu, SRAM_BASE, CPU_DST, nbytes)
    soc_dma = SoC(cfg)
    soc_dma.boot()
    if completion == "polling":
        dma = measure_dma_polling(soc_dma, SRAM_BASE, DMA_DST, nbytes)
    elif completion == "irq":
        dma = measure_dma_irq(soc_dma, SRAM_BASE, DMA_DST, nbytes)
    else:
        raise ValueError(f"unknown completion mode {completion!r}")
    cpu_ticks = cpu["total_ticks"]
    dma_total = dma["total_ticks"]
    row = {
        "transfer_size": nbytes,
        "burst": burst,
        "completion_mode": completion,
        "cpu_ticks": cpu_ticks,  # measured
        "dma_transfer_ticks": dma["transfer_ticks"],  # measured
        "total_ticks": dma_total,  # measured
        "dma_bytes": dma["dma_bytes"],  # measured
        "mem_accesses": dma["mem_acc"],  # measured
        "irq_count": dma["irq"],  # measured
        "stalls": dma["stalls"],  # measured
        "throughput": dma["bytes_per_tick"],  # derived
        "transfer_throughput": dma["transfer_bytes_per_tick"],  # derived
        "cpu_work": {  # measured bus ops + modeled wait interpretation
            "cpu_path_bus_ops": cpu["mem_acc"],  # measured
            "dma_path_bus_ops": dma["mem_acc"],  # measured
        },
        "completion_cost": {  # measured
            "mode": completion,
            "status_reads": dma["completion_cost_reads"],
            "setup_ack_ticks": dma["setup_ack_ticks"],
        },
        "destination_match": True,  # measured (asserted byte compare)
        "cpu_mem_accesses": cpu["mem_acc"],  # measured
        "cpu_irq": cpu["irq"],  # measured
        "cpu_throughput": cpu["bytes_per_tick"],  # derived
        "cpu_ns": int(cpu_ticks * 1000 / mhz),  # derived
        "dma_ns": int(dma_total * 1000 / mhz),  # derived
        "speedup_vs_cpu": cpu_ticks / dma_total if dma_total else 0.0,  # derived
        # Derived (explicitly NOT a hardware counter):
        "cpu_work_avoided_bus_ops": cpu["mem_acc"] - dma["mem_acc"],  # derived
        "provenance": {
            "measured": MEASURED_FIELDS,
            "derived": DERIVED_FIELDS,
            "modeled": MODELED_FIELDS,
        },
    }
    return row


def run_size(config: dict, nbytes: int) -> dict:
    """Legacy helper (v0.3 shape); kept for compatibility."""
    mhz = config.get("cpu_frequency_mhz", 100)
    soc_cpu = SoC(config)
    soc_cpu.boot()
    cpu = measure_cpu(soc_cpu, SRAM_BASE, CPU_DST, nbytes)
    soc_dma = SoC(config)
    soc_dma.boot()
    dma = measure_dma_irq(soc_dma, SRAM_BASE, DMA_DST, nbytes)
    return {
        "nbytes": nbytes,
        "cpu": cpu,
        "dma": dma,
        "cpu_ns": int(cpu["total_ticks"] * 1000 / mhz),
        "dma_ns": int(dma["total_ticks"] * 1000 / mhz),
        "speedup_total": cpu["total_ticks"] / dma["total_ticks"] if dma["total_ticks"] else 0.0,
    }


def _summarize(runs: list[dict], sizes: list[int], bursts: list[int],
               modes: list[str]) -> dict:
    by_size: dict[str, dict] = {}
    for s in sizes:
        rows = [r for r in runs if r["transfer_size"] == s]
        by_size[str(s)] = {
            "cpu_ticks": next(r["cpu_ticks"] for r in rows),
            "best_dma_total_ticks": min(r["total_ticks"] for r in rows),
            "best": min(
                ((r["burst"], r["completion_mode"], r["total_ticks"]) for r in rows),
                key=lambda t: t[2],
            ),
        }
    by_burst: dict[str, dict] = {}
    for b in bursts:
        rows = [r for r in runs if r["burst"] == b]
        by_burst[str(b)] = {
            "min_transfer_ticks": min(r["dma_transfer_ticks"] for r in rows),
            "max_throughput": max(r["throughput"] for r in rows),
        }
    by_completion_mode: dict[str, dict] = {}
    for m in modes:
        rows = [r for r in runs if r["completion_mode"] == m]
        by_completion_mode[m] = {
            "total_ticks_sum": sum(r["total_ticks"] for r in rows),
            "irq_sum": sum(r["irq_count"] for r in rows),
            "mem_sum": sum(r["mem_accesses"] for r in rows),
        }
    crossover: dict[str, object] = {}
    for b in bursts:
        for m in modes:
            rows = sorted(
                (r for r in runs if r["burst"] == b and r["completion_mode"] == m),
                key=lambda r: r["transfer_size"],
            )
            hit = next((r for r in rows if r["total_ticks"] < r["cpu_ticks"]), None)
            key = f"burst{b}/{m}"
            crossover[key] = (
                {"transfer_size": hit["transfer_size"],
                 "cpu_ticks": hit["cpu_ticks"],
                 "dma_total_ticks": hit["total_ticks"]}
                if hit is not None
                else "No crossover observed in tested range."
            )
    return {
        "by_size": by_size,
        "by_burst": by_burst,
        "by_completion_mode": by_completion_mode,
        "crossover": crossover,
        "key_findings": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="CPU vs DMA benchmark, Phase 4 (measured).")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    ap.add_argument("--bursts", default=",".join(map(str, DEFAULT_BURSTS)))
    ap.add_argument("--completion", default="both",
                    choices=("polling", "irq", "both"))
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "results" / "cpu_vs_dma_phase4.json"))
    args = ap.parse_args()

    config = load_config(args.config)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    bursts = [int(b) for b in args.bursts.split(",") if b.strip()]
    modes = list(COMPLETIONS) if args.completion == "both" else [args.completion]
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")
    for s in sizes:
        if s % 4 != 0 or s <= 0:
            raise SystemExit(f"size {s} must be a positive multiple of 4")
        _check_fit(s)

    runs: list[dict] = []
    for rep in range(args.reps):
        for s in sizes:
            for b in bursts:
                for m in modes:
                    row = run_cell(config, s, b, m)
                    row["rep"] = rep
                    runs.append(row)

    # Determinism check across reps (model must repeat exactly).
    det = True
    seen: dict[tuple, set] = {}
    for r in runs:
        key = (r["transfer_size"], r["burst"], r["completion_mode"])
        seen.setdefault(key, set()).add((r["total_ticks"], r["dma_transfer_ticks"]))
    deterministic = all(len(v) == 1 for v in seen.values())
    det = det and deterministic

    payload = {
        "params": {
            "config": pathlib.Path(args.config).name,
            "config_values": {
                "cpu_frequency_mhz": config.get("cpu_frequency_mhz"),
                "dma_burst": config.get("dma_burst"),
                "dma_latency_per_word_ticks": config.get("dma_latency_per_word_ticks"),
                "ram_latency_ticks": config.get("ram_latency_ticks"),
            },
            "transfer_sizes": sizes,
            "burst_sizes": bursts,
            "completion_modes": modes,
            "repetitions": args.reps,
            "dma_formula": "words*latency_per_word + (bursts-1), bursts=ceil(words/burst)",
            "cpu_model": "per-word 1 execute tick + ram_latency_ticks wait ticks",
            "sram_limit_note": "64KB SRAM; single transfers capped at 16KB",
            "deterministic_across_reps": det,
        },
        "runs": runs,
        "summary": _summarize(runs, sizes, bursts, modes),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"config: {payload['params']['config']} sizes={sizes} bursts={bursts} "
          f"modes={modes} reps={args.reps} deterministic={det}")
    print(f"{'bytes':>6} {'burst':>5} {'mode':>7} {'cpu':>7} {'dma_tot':>7} "
          f"{'dma_xf':>7} {'speedup':>7} {'B/t':>6} {'irq':>3} {'mem':>6}")
    # Print rep 0 only for brevity.
    for r in runs:
        if r["rep"] != 0:
            continue
        print(f"{r['transfer_size']:>6} {r['burst']:>5} {r['completion_mode']:>7} "
              f"{r['cpu_ticks']:>7} {r['total_ticks']:>7} {r['dma_transfer_ticks']:>7} "
              f"{r['speedup_vs_cpu']:>7.2f} {r['throughput']:>6.3f} "
              f"{r['irq_count']:>3} {r['mem_accesses']:>6}")
    print("crossover (smallest size with dma_total < cpu_total):")
    for k, v in payload["summary"]["crossover"].items():
        print(f"  {k}: {v}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
