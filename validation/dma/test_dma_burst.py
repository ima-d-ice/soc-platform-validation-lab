"""DMA burst + completion/error IRQ + two-step clear (v0.3).

Burst size is config-only (dma_burst words per burst). Timing:
  words = LEN/4; bursts = ceil(words/burst)
  ticks = words*latency_per_word + (bursts-1)
"""
from __future__ import annotations

import copy
import math

import pytest

from soc.soc import SoC

SRAM_BASE = 0x10000000
DMA_BASE = 0x20002000
SRC = DMA_BASE + 0x00
DST = DMA_BASE + 0x04
LEN = DMA_BASE + 0x08
CTRL = DMA_BASE + 0x0C
STATUS = DMA_BASE + 0x10
IRQ_CLEAR = DMA_BASE + 0x14
ERR_CODE = DMA_BASE + 0x18

INTC_BASE = 0x20003000
INTC_ENABLE = INTC_BASE + 0x00
INTC_PENDING = INTC_BASE + 0x04
INTC_ACK = INTC_BASE + 0x08
INTC_CLEAR = INTC_BASE + 0x0C
INTC_ACTIVE = INTC_BASE + 0x10

IRQ_DMA = 2
IRQ_NONE = 0xFFFFFFFF
BUSY = 1 << 0
DONE = 1 << 1
ERROR = 1 << 2


def _expected_ticks(nbytes: int, burst: int, lat: int) -> int:
    words = math.ceil(nbytes / 4)
    bursts = math.ceil(words / burst)
    return max(1, words * lat + (bursts - 1))


def _start(soc, src, dst, nbytes, irq_en=True):
    soc.write(SRC, src)
    soc.write(DST, dst)
    soc.write(LEN, nbytes)
    soc.write(CTRL, 0x1 | (0x2 if irq_en else 0))


def test_burst_timing_deterministic(soc):
    burst = soc.config["dma_burst"]
    lat = soc.config["dma_latency_per_word_ticks"]
    for nbytes in (16, 64, 256):
        _start(soc, SRAM_BASE, SRAM_BASE + 0x2000, nbytes)
        elapsed = soc.run_until(lambda: soc.read(STATUS) & (DONE | ERROR), max_ticks=5000)
        assert soc.read(STATUS) & DONE
        assert elapsed == _expected_ticks(nbytes, burst, lat)
        soc.write(IRQ_CLEAR, 1)
        # Repeat: identical ticks (deterministic).
        _start(soc, SRAM_BASE, SRAM_BASE + 0x2000, nbytes)
        elapsed2 = soc.run_until(lambda: soc.read(STATUS) & (DONE | ERROR), max_ticks=5000)
        assert elapsed2 == elapsed
        soc.write(IRQ_CLEAR, 1)


def test_burst_size_sensitivity(config):
    nbytes = 64
    lat = config["dma_latency_per_word_ticks"]
    ticks = {}
    for burst in (1, 16):
        cfg = copy.deepcopy(config)
        cfg["dma_burst"] = burst
        s = SoC(cfg)
        s.boot()
        _start(s, SRAM_BASE, SRAM_BASE + 0x2000, nbytes)
        ticks[burst] = s.run_until(lambda: s.read(STATUS) & DONE, max_ticks=5000)
        assert s.read(0x20004008) == nbytes  # same bytes moved
    assert ticks[1] == _expected_ticks(nbytes, 1, lat) == 31
    assert ticks[16] == _expected_ticks(nbytes, 16, lat) == 16
    assert ticks[1] != ticks[16]


def test_completion_irq_two_step_clear(soc):
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    for i in range(4):
        soc.sram_write_word(SRAM_BASE + i * 4, 0xC0FFEE00 | i)
    _start(soc, SRAM_BASE, SRAM_BASE + 0x1000, 16, irq_en=True)
    soc.run_until(lambda: soc.read(STATUS) & DONE, max_ticks=1000)
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    # DMA flag clear alone does NOT clear INTC pending.
    soc.write(IRQ_CLEAR, 1)
    assert not (soc.read(STATUS) & DONE)
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    # ACK moves pending->active; active persists until INTC_CLEAR.
    assert soc.read(INTC_ACK) == IRQ_DMA
    assert soc.read(INTC_ACTIVE) & (1 << IRQ_DMA)
    soc.write(INTC_CLEAR, IRQ_DMA)
    assert not (soc.read(INTC_ACTIVE) & (1 << IRQ_DMA))
    assert soc.read(INTC_ACK) == IRQ_NONE
    # Bytes actually moved.
    for i in range(4):
        assert soc.sram_read_word(SRAM_BASE + 0x1000 + i * 4) == (0xC0FFEE00 | i)


def test_error_irq_and_sticky(soc):
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    soc.write(SRC, 0x30000000)
    soc.write(DST, SRAM_BASE)
    soc.write(LEN, 16)
    soc.write(CTRL, 0x1 | 0x2)
    soc.step(2)
    assert soc.read(STATUS) & ERROR
    assert soc.read(ERR_CODE) == 1
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)  # error raises too
    # Sticky across idle ticks.
    soc.step(10)
    assert soc.read(STATUS) & ERROR
    # Two-step clear.
    soc.write(IRQ_CLEAR, 1)
    assert not (soc.read(STATUS) & ERROR)
    assert soc.read(ERR_CODE) == 0
    assert soc.read(INTC_ACK) == IRQ_DMA
    soc.write(INTC_CLEAR, IRQ_DMA)


def test_overlap_uses_memmove(soc):
    src = SRAM_BASE
    dst = SRAM_BASE + 4  # overlapping forward copy
    words = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
    for i, w in enumerate(words):
        soc.sram_write_word(src + i * 4, w)
    _start(soc, src, dst, 16, irq_en=False)
    soc.run_until(lambda: soc.read(STATUS) & DONE, max_ticks=1000)
    # memmove: dst gets the ORIGINAL src bytes.
    for i, w in enumerate(words):
        assert soc.sram_read_word(dst + i * 4) == w
    soc.write(IRQ_CLEAR, 1)


def test_done_sticky_until_next_start(soc):
    _start(soc, SRAM_BASE, SRAM_BASE + 0x1000, 16, irq_en=False)
    soc.run_until(lambda: soc.read(STATUS) & DONE, max_ticks=1000)
    soc.step(10)
    assert soc.read(STATUS) & DONE  # sticky across idle
    _start(soc, SRAM_BASE, SRAM_BASE + 0x1000, 16, irq_en=False)
    assert soc.read(STATUS) & BUSY  # next START clears DONE, sets BUSY
    soc.run_until(lambda: soc.read(STATUS) & DONE, max_ticks=1000)
