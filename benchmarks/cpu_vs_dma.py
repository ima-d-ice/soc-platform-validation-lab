#!/usr/bin/env python3
"""CPU memcpy vs DMA transfer benchmark (v0.3): real model measurements.

Method (deterministic, nothing synthesised):
- CPU path: word-by-word soc.read + soc.write loop. Each word costs
  1 execute tick + ram_latency_ticks wait ticks via soc.step() (config
  `ram_latency_ticks`; base = 2, so 3 ticks/word). MEM_ACC/STALLS/CYCLES
  come from the model itself.
- DMA path: program SRC/DST/LEN (bus writes), START with IRQ_ENABLE,
  run_until DONE (transfer ticks follow the spec burst formula), then
  ACK + DMA.IRQ_CLEAR + INTC.CLEAR. Both transfer_ticks (run_until only)
  and total_ticks (setup + transfer + ack/clear) are reported.
- Correctness: destination bytes are read back and compared on every run.
- ns derived from ticks via cpu_frequency_mhz (informational only).

Writes JSON to results/cpu_vs_dma.json (gitignored).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soc.soc import SoC, load_config

SRAM_BASE = 0x10000000
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

DEFAULT_SIZES = (16, 64, 256, 1024, 4096)


def _pattern(nbytes: int) -> list[int]:
    nwords = nbytes // 4
    return [0xB1000000 | (i & 0xFFFFFF) for i in range(nwords)]


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
    # Read back for correctness (outside the timed region accounting?
    # These reads DO count in `after`, so re-snapshot deltas first).
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


def measure_dma(soc: SoC, src: int, dst: int, nbytes: int) -> dict:
    """Run DMA transfer with completion IRQ on a booted SoC."""
    assert nbytes % 4 == 0 and nbytes > 0
    words = _pattern(nbytes)
    for i, w in enumerate(words):
        soc.sram_write_word(src + i * 4, w)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    before = _snapshot(soc)
    soc.write(D_SRC, src)
    soc.write(D_DST, dst)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1 | 0x2)  # START | IRQ_ENABLE
    transfer_ticks = soc.run_until(
        lambda: soc.read(D_STATUS) & (DONE | ERROR), max_ticks=100000
    )
    assert soc.read(D_STATUS) & DONE, "DMA did not complete"
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    acked = soc.read(INTC_ACK)
    assert acked == IRQ_DMA
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
        "total_ticks": total,
        "transfer_ticks": transfer_ticks,
        "setup_ack_ticks": total - transfer_ticks,
        "cycles": d["cycles"],
        "mem_acc": d["mem_acc"],
        "irq": d["irq"],
        "dma_bytes": d["dma_bytes"],
        "cpu_free_ticks": transfer_ticks,
        "bytes_per_tick": nbytes / total if total else 0.0,
        "transfer_bytes_per_tick": nbytes / transfer_ticks if transfer_ticks else 0.0,
    }


def run_size(config: dict, nbytes: int) -> dict:
    mhz = config.get("cpu_frequency_mhz", 100)
    soc_cpu = SoC(config)
    soc_cpu.boot()
    cpu = measure_cpu(soc_cpu, SRAM_BASE, CPU_DST, nbytes)
    soc_dma = SoC(config)
    soc_dma.boot()
    dma = measure_dma(soc_dma, SRAM_BASE, DMA_DST, nbytes)
    return {
        "nbytes": nbytes,
        "cpu": cpu,
        "dma": dma,
        "cpu_ns": int(cpu["total_ticks"] * 1000 / mhz),
        "dma_ns": int(dma["total_ticks"] * 1000 / mhz),
        "speedup_total": cpu["total_ticks"] / dma["total_ticks"] if dma["total_ticks"] else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="CPU vs DMA benchmark (measured).")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    ap.add_argument("--out", default=str(ROOT / "results" / "cpu_vs_dma.json"))
    args = ap.parse_args()

    config = load_config(args.config)
    sizes = tuple(int(s) for s in args.sizes.split(",") if s.strip())
    results = [run_size(config, n) for n in sizes]
    payload = {
        "config": pathlib.Path(args.config).name,
        "cpu_frequency_mhz": config.get("cpu_frequency_mhz"),
        "dma_burst": config.get("dma_burst"),
        "dma_latency_per_word_ticks": config.get("dma_latency_per_word_ticks"),
        "ram_latency_ticks": config.get("ram_latency_ticks"),
        "method": {
            "cpu_per_word_ticks": 1 + int(config.get("ram_latency_ticks", 2)),
            "dma_formula": "words*latency_per_word + (bursts-1), bursts=ceil(words/burst)",
        },
        "results": results,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"config: {payload['config']} burst={payload['dma_burst']} "
          f"dma_lat={payload['dma_latency_per_word_ticks']} ram_lat={payload['ram_latency_ticks']}")
    print(f"{'bytes':>6} {'cpu_ticks':>9} {'dma_total':>9} {'dma_xfer':>8} "
          f"{'speedup':>7} {'cpu_B/t':>7} {'dma_B/t':>7} {'irq_c/d':>7}")
    for r in results:
        c, d = r["cpu"], r["dma"]
        print(f"{r['nbytes']:>6} {c['total_ticks']:>9} {d['total_ticks']:>9} "
              f"{d['transfer_ticks']:>8} {r['speedup_total']:>7.2f} "
              f"{c['bytes_per_tick']:>7.3f} {d['bytes_per_tick']:>7.3f} "
              f"{c['irq']}/{d['irq']:>5}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
