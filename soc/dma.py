"""DMA engine: burst transfer + completion/error IRQ (v0.3).

Single channel. CTRL.START auto-clears, STATUS sticky until next START or
IRQ_CLEAR, memmove semantics for overlap. Burst size is config-only
(configs/*.yaml `dma_burst`, words per burst); there is no BURST register,
preserving the register map.

Timing (deterministic):
  words = LEN/4; bursts = ceil(words / burst)
  ticks = words * latency_per_word + (bursts - 1) * 1
The +1 per extra burst is the arbitration overhead. Completion raises the
configured INTC line iff IRQ_ENABLE was latched at START. Errors are
synchronous: the failing START sets ERROR + ERR_CODE immediately (no
BUSY), raises the IRQ iff enabled, and stays sticky until next START or
IRQ_CLEAR. Clearing requires two steps: DMA.IRQ_CLEAR clears DMA flags;
INTC.CLEAR clears the pending bit.

Validation is capability-driven (see soc/dma_caps.py): alignment, length,
and max_transfer come from DmaCaps; endpoint regions come from the
platform region table. Error split: ERR_LEN/ERR_ALIGN/ERR_ADDR mean
invalid driver-API use; ERR_UNSUPPORTED(4, additive) means a mapped
endpoint or length outside this DMA's platform capabilities.
"""
from __future__ import annotations

import math

from .bus import BusError
from .dma_caps import (ERR_UNSUPPORTED, DmaCaps, dma_direction_supported,
                       endpoint_type)
from .memory import PERM_R, PERM_W, SRAM, MemoryRegion

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
# ERR_UNSUPPORTED (=4) is imported from soc/dma_caps.py and re-exported here.

IRQ_LINE = 2  # default; SoC passes the platform IRQ map line instead


def _default_regions(sram_base: int, sram_size: int) -> list[MemoryRegion]:
    return [MemoryRegion("sram", sram_base, sram_size, SRAM,
                         PERM_R | PERM_W)]


class Dma:
    def __init__(self, *, sram_base: int, sram_size: int, latency_per_word: int = 1,
                 burst: int = 4,
                 regions: list[MemoryRegion] | None = None,
                 caps: DmaCaps | None = None,
                 irq_line: int = IRQ_LINE,
                 intc=None, perf=None, mem_reader=None, mem_writer=None):
        self.sram_base = sram_base
        self.sram_size = sram_size
        self.latency_per_word = max(1, latency_per_word)
        self.burst = max(1, burst)
        self.regions = regions if regions is not None else _default_regions(
            sram_base, sram_size)
        self.caps = caps if caps is not None else DmaCaps()
        self.irq_line = irq_line
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

    # -- validation (capability-driven; order is part of the contract) --

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
            self._intc.raise_irq(self.irq_line)

    def _start(self, irq_enable: bool) -> None:
        if self.busy:
            if self._perf is not None:
                self._perf.count_stall()
            return
        self._irq_enable_latched = irq_enable
        self.done = False
        self.error = False
        self.err_code = ERR_NONE
        align = max(1, self.caps.alignment)
        # Invalid driver-API use first: length, alignment.
        if self.length == 0 or (align > 1 and self.length % align != 0):
            self._fail(ERR_LEN)
            return
        if align > 1 and (self.src % align != 0 or self.dst % align != 0):
            self._fail(ERR_ALIGN)
            return
        # Platform limits next: max transfer, then endpoint support.
        if (self.caps.max_transfer is not None
                and self.length > self.caps.max_transfer):
            self._fail(ERR_UNSUPPORTED)
            return
        src_type = endpoint_type(self.regions, self.src, self.length)
        dst_type = endpoint_type(self.regions, self.dst, self.length)
        if src_type is None or dst_type is None:
            self._fail(ERR_ADDR)
            return
        if not dma_direction_supported(self.caps, src_type, dst_type):
            self._fail(ERR_UNSUPPORTED)
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
        # Complete with memmove semantics. A post-START address change
        # bypasses START-time validation, so completion I/O faults convert
        # to ERROR/ERR_ADDR deterministically instead of escaping the tick.
        assert self._reader is not None and self._writer is not None
        try:
            payload = self._reader(self.src, self.length)
            self._writer(self.dst, payload)
        except BusError:
            self.busy = False
            self.done = False
            self.error = True
            self.err_code = ERR_ADDR
            if self._irq_enable_latched and self._intc is not None:
                self._intc.raise_irq(self.irq_line)
            return
        self.busy = False
        self.done = True
        self.error = False
        if self._perf is not None:
            self._perf.count_dma(self.length)
        if self._irq_enable_latched and self._intc is not None:
            self._intc.raise_irq(self.irq_line)
