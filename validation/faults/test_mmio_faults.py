"""Invalid-MMIO validation: every error case in soc-spec.md §3 behaves
deterministically (BusError + one STALLS tick), with no state corruption."""
from __future__ import annotations

import pytest

from soc.bus import BusError

ROM_BASE = 0x00000000
SRAM_BASE = 0x10000000
UART_BASE = 0x20000000
TIMER_BASE = 0x20001000
DMA_BASE = 0x20002000
INTC_BASE = 0x20003000

PERF_STALLS = 0x20004010
PERF_MEM = 0x20004004


def _stalls(soc):
    return soc.read(PERF_STALLS)


def test_unmapped_read_and_write(soc):
    before = _stalls(soc)
    with pytest.raises(BusError):
        soc.read(0x30000000)
    with pytest.raises(BusError):
        soc.write(0x30000000, 1)
    assert _stalls(soc) == before + 2  # one stall per rejected access


def test_ro_write_rejected(soc):
    for addr in (
        ROM_BASE,  # ROM read-only at run time
        UART_BASE + 0x08,  # UART STATUS
        TIMER_BASE + 0x08,  # TIMER VALUE
        DMA_BASE + 0x10,  # DMA STATUS
        DMA_BASE + 0x18,  # DMA ERR_CODE
        INTC_BASE + 0x04,  # INTC PENDING
        INTC_BASE + 0x10,  # INTC ACTIVE
    ):
        with pytest.raises(BusError):
            soc.write(addr, 0xFFFFFFFF)


def test_wo_read_rejected(soc):
    for addr in (
        UART_BASE + 0x00,  # UART TXDATA
        TIMER_BASE + 0x10,  # TIMER IRQ_CLEAR
        DMA_BASE + 0x14,  # DMA IRQ_CLEAR
        INTC_BASE + 0x0C,  # INTC CLEAR
    ):
        with pytest.raises(BusError):
            soc.read(addr)


def test_invalid_offset_rejected(soc):
    for addr in (
        UART_BASE + 0x1C,  # beyond UART regs
        TIMER_BASE + 0x1C,
        DMA_BASE + 0x1C,
        INTC_BASE + 0x1C,
        0x20004018,  # beyond PERF regs
    ):
        with pytest.raises(BusError):
            soc.read(addr)


def test_unaligned_rejected(soc):
    with pytest.raises(BusError):
        soc.read(SRAM_BASE + 1)
    with pytest.raises(BusError):
        soc.write(UART_BASE + 0x0C + 2, 0)


def test_out_of_range_address(soc):
    with pytest.raises(BusError):
        soc.read(0xFFFFFFFF & ~0x3)
    with pytest.raises(BusError):
        soc.write(0x50000000, 0)


def test_rejected_access_leaves_state_intact(soc):
    soc.write(UART_BASE + 0x0C, 0x1)  # UART ENABLE
    mem_before = soc.read(PERF_MEM)
    for bad_op in (
        lambda: soc.write(UART_BASE + 0x08, 0xFF),
        lambda: soc.read(UART_BASE + 0x00),
        lambda: soc.read(0x30000000),
    ):
        with pytest.raises(BusError):
            bad_op()
    assert soc.read(UART_BASE + 0x0C) == 0x1  # CTRL untouched
    assert soc.read(PERF_MEM) > mem_before  # rejected ops still counted
