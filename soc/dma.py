"""DMA engine: burst transfer + completion/error IRQ (v0.3).

Single channel. CTRL.START auto-clears, STATUS sticky until next START or
IRQ_CLEAR, memmove semantics for overlap. Burst size is config-only
(configs/*.yaml `dma_burst`, words per burst); there is no BURST register,
preserving the register map.

Timing (deterministic):
  words = LEN/4; bursts = ceil(words / burst)
  ticks = words * latency_per_word + (bursts - 1) * 1
The +1 per extra burst is the arbitration overhead. Completion raises INTC
line 2 iff IRQ_ENABLE was latched at START. Errors are synchronous: the
failing START sets ERROR + ERR_CODE immediately (no BUSY), raises the IRQ
iff enabled, and stays sticky until next START or IRQ_CLEAR. Clearing
requires two steps: DMA.IRQ_CLEAR clears DMA flags; INTC.CLEAR(2) clears
the pending bit.
"""
from __future__ import annotations

import math

from .bus import BusError

SRC_OFF = 0x00
DST_OFF = 0x04
LEN_OFF = 0x08
CTRL_OFF = 0x0C
STATUS_OFF = 0x10
IRQ_CLEAR_OFF = 0x14
ERR_CODE_OFF = 0x18

CTRL_START = 1 << 0
CTRL_IRQ_ENABLE = 1 << 1

STATUS_BUSY = 1 << 0
STATUS_DONE = 1 << 1
STATUS_ERROR = 1 << 2

ERR_NONE = 0
ERR_ADDR = 1
ERR_ALIGN = 2
ERR_LEN = 3

IRQ_LINE = 2


class Dma:
    def __init__(self, *, sram_base: int, sram_size: int, latency_per_word: int = 1,
                 burst: int = 4,
                 intc=None, perf=None, mem_reader=None, mem_writer=None):
        self.sram_base = sram_base
        self.sram_size = sram_size
        self.latency_per_word = max(1, latency_per_word)
        self.burst = max(1, burst)
        self._intc = intc
        self._perf = perf
        # Callables bridging to SRAM without import cycles:
        # reader(addr, length) -> bytes ; writer(addr, payload) -> None
        self._reader = mem_reader
        self._writer = mem_writer
        self.src = 0
        self.dst = 0
        self.length = 0
        self.ctrl = 0
        self.busy = False
        self.done = False
        self.error = False
        self.err_code = ERR_NONE
        self._remaining = 0
        self._irq_enable_latched = False
        # Fault hook (Phase 5): when True, a BUSY transfer never counts down
        # (stuck-busy). Default off; reset clears it. No register change.
        self.fault_stuck_busy = False

    def reset(self) -> None:
        self.src = 0
        self.dst = 0
        self.length = 0
        self.ctrl = 0
        self.busy = False
        self.done = False
        self.error = False
        self.err_code = ERR_NONE
        self._remaining = 0
        self._irq_enable_latched = False
        self.fault_stuck_busy = False

    # -- validation --
    def _in_sram(self, addr: int, length: int) -> bool:
        if length <= 0:
            return False
        base, top = self.sram_base, self.sram_base + self.sram_size
        return base <= addr and addr + length <= top

    def read(self, offset: int) -> int:
        if offset == SRC_OFF:
            return self.src & 0xFFFFFFFF
        if offset == DST_OFF:
            return self.dst & 0xFFFFFFFF
        if offset == LEN_OFF:
            return self.length & 0xFFFFFFFF
        if offset == CTRL_OFF:
            return self.ctrl & 0xFFFFFFFF
        if offset == STATUS_OFF:
            s = 0
            if self.busy:
                s |= STATUS_BUSY
            if self.done:
                s |= STATUS_DONE
            if self.error:
                s |= STATUS_ERROR
            return s
        if offset == ERR_CODE_OFF:
            return self.err_code & 0xFFFFFFFF
        if offset == IRQ_CLEAR_OFF:
            raise BusError("DMA: read from write-only IRQ_CLEAR")
        raise BusError(f"DMA: invalid offset 0x{offset:X}")

    def write(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if offset == SRC_OFF:
            self.src = value
            return
        if offset == DST_OFF:
            self.dst = value
            return
        if offset == LEN_OFF:
            self.length = value
            return
        if offset == CTRL_OFF:
            irq_en = bool(value & CTRL_IRQ_ENABLE)
            if value & CTRL_START:
                self._start(irq_en)
            self.ctrl = (value & ~CTRL_START) | (CTRL_IRQ_ENABLE if irq_en else 0)
            return
        if offset == IRQ_CLEAR_OFF:
            self.done = False
            self.error = False
            self.err_code = ERR_NONE
            return
        if offset in (STATUS_OFF, ERR_CODE_OFF):
            raise BusError(f"DMA: write to read-only reg 0x{offset:X}")
        raise BusError(f"DMA: invalid offset 0x{offset:X}")

    def _fail(self, code: int) -> None:
        self.busy = False
        self.done = False
        self.error = True
        self.err_code = code
        if self._irq_enable_latched and self._intc is not None:
            self._intc.raise_irq(IRQ_LINE)

    def _start(self, irq_enable: bool) -> None:
        if self.busy:
            if self._perf is not None:
                self._perf.count_stall()
            return
        self._irq_enable_latched = irq_enable
        self.done = False
        self.error = False
        self.err_code = ERR_NONE
        # Validate.
        if self.length == 0 or self.length % 4 != 0:
            self._fail(ERR_LEN)
            return
        if self.src % 4 != 0 or self.dst % 4 != 0:
            self._fail(ERR_ALIGN)
            return
        if not self._in_sram(self.src, self.length) or not self._in_sram(self.dst, self.length):
            self._fail(ERR_ADDR)
            return
        self.busy = True
        words = math.ceil(self.length / 4)
        bursts = math.ceil(words / self.burst)
        self._remaining = max(1, words * self.latency_per_word + (bursts - 1))

    def step(self) -> None:
        if not self.busy:
            return
        if self.fault_stuck_busy:
            return  # stuck-busy fault: countdown frozen, stays BUSY
        self._remaining -= 1
        if self._remaining > 0:
            return
        # Complete with memmove semantics.
        assert self._reader is not None and self._writer is not None
        payload = self._reader(self.src, self.length)
        self._writer(self.dst, payload)
        self.busy = False
        self.done = True
        self.error = False
        if self._perf is not None:
            self._perf.count_dma(self.length)
        if self._irq_enable_latched and self._intc is not None:
            self._intc.raise_irq(IRQ_LINE)
