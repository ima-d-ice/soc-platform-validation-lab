"""CPU-vs-DMA focused checks: correctness, determinism, scaling (v0.3).

Full 16B–4KB sweep lives in benchmarks/cpu_vs_dma.py; this file asserts the
helpers on two fast points only. No performance outcome is assumed.
"""
from __future__ import annotations

from benchmarks.cpu_vs_dma import CPU_DST, DMA_DST, SRAM_BASE, measure_cpu, measure_dma


def test_paths_move_identical_bytes(soc):
    cpu = measure_cpu(soc, SRAM_BASE, CPU_DST, 16)
    assert cpu["irq"] == 0
    dma = measure_dma(soc, SRAM_BASE, DMA_DST, 16)
    assert dma["irq"] == 1
    assert dma["dma_bytes"] == 16
    # Same source pattern -> identical destinations.
    for i in range(4):
        assert soc.sram_read_word(CPU_DST + i * 4) == soc.sram_read_word(DMA_DST + i * 4)


def test_deterministic_ticks(config):
    from soc.soc import SoC

    first, second = [], []
    for store in (first, second):
        s = SoC(config)
        s.boot()
        store.append(measure_cpu(s, SRAM_BASE, CPU_DST, 1024)["total_ticks"])
        s2 = SoC(config)
        s2.boot()
        store.append(measure_dma(s2, SRAM_BASE, DMA_DST, 1024)["total_ticks"])
    assert first == second


def test_ticks_grow_with_size(soc):
    c16 = measure_cpu(soc, SRAM_BASE, CPU_DST, 16)["total_ticks"]
    c256 = measure_cpu(soc, SRAM_BASE, CPU_DST, 256)["total_ticks"]
    d16 = measure_dma(soc, SRAM_BASE, DMA_DST, 16)["total_ticks"]
    d256 = measure_dma(soc, SRAM_BASE, DMA_DST, 256)["total_ticks"]
    assert c256 > c16 > 0
    assert d256 > d16 > 0
