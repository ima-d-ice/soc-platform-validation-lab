"""Performance monitor: real model counters (never synthesised)."""
from __future__ import annotations

from ...bus import BusError

PERF_CYCLES_OFF = 0x00
PERF_MEM_ACC_OFF = 0x04
PERF_DMA_BYTES_OFF = 0x08
PERF_IRQ_COUNT_OFF = 0x0C
PERF_STALLS_OFF = 0x10
PERF_CTRL_OFF = 0x14

CTRL_ENABLE = 1 << 0
CTRL_RESET = 1 << 1


class Perf:
    def __init__(self):
        self.cycles = 0
        self.mem_acc = 0
        self.dma_bytes = 0
        self.irq_count = 0
        self.stalls = 0
        self.enabled = False
        self.ctrl = 0

    def reset_counters(self) -> None:
        self.cycles = 0
        self.mem_acc = 0
        self.dma_bytes = 0
        self.irq_count = 0
        self.stalls = 0

    # -- counting helpers (only count when enabled, except reset) --
    def tick(self) -> None:
        if self.enabled:
            self.cycles += 1

    def count_mem(self) -> None:
        if self.enabled:
            self.mem_acc += 1

    def count_stall(self, n: int = 1) -> None:
        if self.enabled:
            self.stalls += n

    def count_dma(self, nbytes: int) -> None:
        if self.enabled:
            self.dma_bytes += nbytes

    def count_irq(self) -> None:
        if self.enabled:
            self.irq_count += 1

    # -- MMIO interface --
    def read(self, offset: int) -> int:
        if offset == PERF_CYCLES_OFF:
            return self.cycles & 0xFFFFFFFF
        if offset == PERF_MEM_ACC_OFF:
            return self.mem_acc & 0xFFFFFFFF
        if offset == PERF_DMA_BYTES_OFF:
            return self.dma_bytes & 0xFFFFFFFF
        if offset == PERF_IRQ_COUNT_OFF:
            return self.irq_count & 0xFFFFFFFF
        if offset == PERF_STALLS_OFF:
            return self.stalls & 0xFFFFFFFF
        if offset == PERF_CTRL_OFF:
            return self.ctrl & 0xFFFFFFFF
        raise BusError(f"PERF: invalid offset 0x{offset:X}")

    def write(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if offset == PERF_CYCLES_OFF:
            self.cycles = value
            return
        if offset == PERF_MEM_ACC_OFF:
            self.mem_acc = value
            return
        if offset == PERF_DMA_BYTES_OFF:
            self.dma_bytes = value
            return
        if offset == PERF_IRQ_COUNT_OFF:
            self.irq_count = value
            return
        if offset == PERF_STALLS_OFF:
            self.stalls = value
            return
        if offset == PERF_CTRL_OFF:
            self.ctrl = value
            self.enabled = bool(value & CTRL_ENABLE)
            if value & CTRL_RESET:
                self.reset_counters()
            return
        raise BusError(f"PERF: invalid offset 0x{offset:X}")
