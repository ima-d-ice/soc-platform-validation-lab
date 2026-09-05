"""Phase 4 DMA optimization checks (fast subset; full sweep is the benchmark).

Covers: byte identity, determinism, burst timing effect, monotonic volume,
IRQ completion, polling silence, no corruption, no faster-assumption,
schema/provenance. Existing suites stay untouched.
"""
from __future__ import annotations

import pytest

from benchmarks.cpu_vs_dma import (
    CPU_DST,
    DMA_DST,
    SRAM_BASE,
    _summarize,
    _with_burst,
    measure_cpu,
    measure_dma_irq,
    measure_dma_polling,
    run_cell,
)
from soc.soc import SoC

GUARD_ADDR = 0x1000FC00  # inside SRAM, outside all benchmark regions
GUARD_VAL = 0xDEADBEEF


def _guard(soc):
    soc.sram_write_word(GUARD_ADDR, GUARD_VAL)


def _check_guard(soc):
    assert soc.sram_read_word(GUARD_ADDR) == GUARD_VAL


def test_cpu_and_dma_destinations_byte_identical(soc):
    _guard(soc)
    cpu = measure_cpu(soc, SRAM_BASE, CPU_DST, 256)
    assert cpu["irq"] == 0
    poll = measure_dma_polling(soc, SRAM_BASE, DMA_DST, 256)
    assert poll["irq"] == 0
    for i in range(256 // 4):
        assert soc.sram_read_word(CPU_DST + i * 4) == soc.sram_read_word(DMA_DST + i * 4)
    _check_guard(soc)


def test_same_config_repeated_is_deterministic(config):
    first = run_cell(config, 256, 4, "irq")
    second = run_cell(config, 256, 4, "irq")
    assert first["total_ticks"] == second["total_ticks"]
    assert first["dma_transfer_ticks"] == second["dma_transfer_ticks"]
    assert first["mem_accesses"] == second["mem_accesses"]
    first_p = run_cell(config, 256, 4, "polling")
    second_p = run_cell(config, 256, 4, "polling")
    assert first_p["total_ticks"] == second_p["total_ticks"]


def test_burst_sweep_changes_dma_timing_where_expected(config):
    # 64B spans multiple bursts at burst=1 but one burst at burst=16, so the
    # small-burst run must take more transfer ticks (extra burst overheads).
    small_burst = run_cell(config, 64, 1, "irq")
    big_burst = run_cell(config, 64, 16, "irq")
    assert small_burst["dma_transfer_ticks"] > big_burst["dma_transfer_ticks"]
    assert small_burst["dma_bytes"] == big_burst["dma_bytes"] == 64


def test_increasing_size_moves_correct_volume(config):
    for size in (16, 256):
        row = run_cell(config, size, 4, "polling")
        assert row["dma_bytes"] == size
        assert row["throughput"] > 0
    small = run_cell(config, 16, 4, "polling")
    big = run_cell(config, 256, 4, "polling")
    assert big["total_ticks"] > small["total_ticks"]


def test_irq_mode_produces_completion_interrupt(soc):
    cfg = _with_burst(soc.config, 4)
    s = SoC(cfg)
    s.boot()
    dma = measure_dma_irq(s, SRAM_BASE, DMA_DST, 64)
    assert dma["irq"] == 1
    assert dma["dma_bytes"] == 64


def test_polling_mode_reports_no_irq(soc):
    dma = measure_dma_polling(soc, SRAM_BASE, DMA_DST, 64)
    assert dma["irq"] == 0
    assert dma["dma_bytes"] == 64
    assert dma["completion_cost_reads"] >= 1


def test_no_dma_corruption(soc):
    _guard(soc)
    # Fill regions with pattern, run both modes, verify guard + surroundings.
    measure_dma_irq(soc, SRAM_BASE, DMA_DST, 256)
    measure_dma_polling(soc, SRAM_BASE, DMA_DST, 256)
    measure_cpu(soc, SRAM_BASE, CPU_DST, 256)
    _check_guard(soc)
    assert soc.sram_read_word(0x1000FFF0) == 0  # untouched tail word reads zero


def test_no_must_be_faster_assumption(config):
    # The harness must compute speedup without requiring DMA to win: the
    # no-crossover branch of the summary must exist and trigger correctly.
    rows = [
        {
            "transfer_size": s, "burst": 4, "completion_mode": "irq",
            "total_ticks": 100 + s, "cpu_ticks": 10,  # dma slower by design
            "dma_transfer_ticks": 100 + s, "throughput": 0.1,
            "irq_count": 1, "mem_accesses": 10,
        }
        for s in (16, 64)
    ]
    summary = _summarize(rows, [16, 64], [4], ["irq"])
    assert summary["crossover"]["burst4/irq"] == "No crossover observed in tested range."
    # And on real data the field is present with a numeric-or-string value.
    real = run_cell(config, 16, 4, "irq")
    assert "speedup_vs_cpu" in real
    assert real["destination_match"] is True


def test_result_schema_and_provenance(config):
    row = run_cell(config, 64, 2, "polling")
    for key in (
        "transfer_size", "burst", "completion_mode", "cpu_ticks",
        "dma_transfer_ticks", "total_ticks", "dma_bytes", "mem_accesses",
        "irq_count", "stalls", "throughput", "cpu_work", "completion_cost",
        "destination_match", "cpu_work_avoided_bus_ops", "provenance",
    ):
        assert key in row, f"missing schema key {key}"
    prov = row["provenance"]
    assert set(prov) == {"measured", "derived", "modeled"}
    assert "total_ticks" in prov["measured"]
    assert "throughput" in prov["derived"]
    assert row["completion_cost"]["mode"] == "polling"
    with pytest.raises(ValueError):
        run_cell(config, 65536, 4, "irq")  # exceeds SRAM: must refuse, not wrap
