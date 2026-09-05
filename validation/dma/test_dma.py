"""DMA validation: single-transfer completion + error handling.

Burst/chained modes deferred.
"""
from __future__ import annotations

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

IRQ_DMA = 2

BUSY = 1 << 0
DONE = 1 << 1
ERROR = 1 << 2


def _pattern(nwords: int) -> list[int]:
    return [0xA5000000 | i for i in range(nwords)]


def test_dma_completes(soc):
    src, dst, nwords = SRAM_BASE, SRAM_BASE + 0x1000, 16
    words = _pattern(nwords)
    for i, w in enumerate(words):
        soc.sram_write_word(src + i * 4, w)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    soc.write(SRC, src)
    soc.write(DST, dst)
    soc.write(LEN, nwords * 4)
    soc.write(CTRL, 0x1 | 0x2)  # START | IRQ_ENABLE
    soc.run_until(lambda: soc.read(STATUS) & (DONE | ERROR), max_ticks=1000)
    assert soc.read(STATUS) & DONE
    assert not (soc.read(STATUS) & ERROR)
    for i, w in enumerate(words):
        assert soc.sram_read_word(dst + i * 4) == w
    assert soc.read(ERR_CODE) == 0
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    assert soc.read(INTC_ACK) == IRQ_DMA
    soc.write(INTC_CLEAR, IRQ_DMA)
    soc.write(IRQ_CLEAR, 1)
    # PERF counted real bytes.
    assert soc.read(0x20004008) == nwords * 4  # PERF DMA_BYTES


def test_dma_invalid_address(soc):
    soc.write(SRC, 0x30000000)
    soc.write(DST, SRAM_BASE)
    soc.write(LEN, 16)
    soc.write(CTRL, 0x1)
    soc.step(2)
    assert soc.read(STATUS) & ERROR
    assert soc.read(ERR_CODE) == 1


def test_dma_misaligned(soc):
    soc.write(SRC, SRAM_BASE + 1)
    soc.write(DST, SRAM_BASE + 0x1000)
    soc.write(LEN, 16)
    soc.write(CTRL, 0x1)
    soc.step(2)
    assert soc.read(STATUS) & ERROR
    assert soc.read(ERR_CODE) == 2


def test_dma_bad_length(soc):
    for bad in (0, 3, 6):
        soc.write(SRC, SRAM_BASE)
        soc.write(DST, SRAM_BASE + 0x1000)
        soc.write(LEN, bad)
        soc.write(CTRL, 0x1)
        soc.step(2)
        assert soc.read(STATUS) & ERROR, f"len={bad}"
        assert soc.read(ERR_CODE) == 3
        soc.write(IRQ_CLEAR, 1)


def test_dma_start_while_busy_ignored(soc):
    src, dst = SRAM_BASE, SRAM_BASE + 0x2000
    soc.write(SRC, src)
    soc.write(DST, dst)
    soc.write(LEN, 64)
    soc.write(CTRL, 0x1)
    assert soc.read(STATUS) & BUSY
    stalls_before = soc.read(0x20004010)  # PERF STALLS
    soc.write(CTRL, 0x1)  # second START while busy
    assert soc.read(STATUS) & BUSY
    assert soc.read(0x20004010) >= stalls_before + 1
    soc.run_until(lambda: soc.read(STATUS) & DONE, max_ticks=1000)
