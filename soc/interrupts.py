"""Interrupt controller: enable/pending/active + read-to-ack (v0.2, complete).

Fixed priority: TIMER(1) > DMA(2) > UART(0). Non-preemptive, queued.

Semantics (deterministic):
- raise_irq sets the PENDING bit (idempotent/coalesced: N raises before an
  ACK still yield exactly one pending bit and one ACK).
- ACK reads the highest pending+enabled line, atomically clears its PENDING
  bit and sets its ACTIVE bit, counts one PERF IRQ. Spurious ACK (nothing
  pending+enabled) returns IRQ_NONE and counts nothing.
- CLEAR takes an irq number 0..2 and clears its ACTIVE bit. Out-of-range
  numbers are ignored (no fault). Clearing an inactive line is a no-op.
- ENABLE gates ACK only; PENDING still records while disabled.
- No nesting/preemption: a second source pending while one is ACTIVE stays
  pending until ACKed in priority order.
"""
from __future__ import annotations

from .bus import BusError

ENABLE_OFF = 0x00
PENDING_OFF = 0x04
ACK_OFF = 0x08
CLEAR_OFF = 0x0C
ACTIVE_OFF = 0x10

IRQ_UART = 0
IRQ_TIMER = 1
IRQ_DMA = 2
IRQ_NONE = 0xFFFFFFFF
N_LINES = 3

# Highest first.
PRIORITY_ORDER = (IRQ_TIMER, IRQ_DMA, IRQ_UART)


class Intc:
    def __init__(self, perf=None):
        self.enable = 0
        self.pending = 0
        self.active = 0
        self._perf = perf

    def reset(self) -> None:
        self.enable = 0
        self.pending = 0
        self.active = 0

    def raise_irq(self, line: int) -> None:
        if 0 <= line < N_LINES:
            self.pending |= 1 << line

    def _highest(self) -> int:
        gated = self.pending & self.enable & 0x7
        for line in PRIORITY_ORDER:
            if gated & (1 << line):
                return line
        return -1

    def read(self, offset: int) -> int:
        if offset == ENABLE_OFF:
            return self.enable & 0xFFFFFFFF
        if offset == PENDING_OFF:
            return self.pending & 0xFFFFFFFF
        if offset == ACTIVE_OFF:
            return self.active & 0xFFFFFFFF
        if offset == ACK_OFF:
            line = self._highest()
            if line < 0:
                return IRQ_NONE
            self.pending &= ~(1 << line)
            self.active |= 1 << line
            if self._perf is not None:
                self._perf.count_irq()
            return line & 0xFFFFFFFF
        raise BusError(f"INTC: invalid offset 0x{offset:X}")

    def write(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if offset == ENABLE_OFF:
            self.enable = value & 0x7
            return
        if offset == CLEAR_OFF:
            line = value & 0xFFFFFFFF
            if line < N_LINES:
                self.active &= ~(1 << line)
            return
        if offset in (PENDING_OFF, ACK_OFF, ACTIVE_OFF):
            raise BusError(f"INTC: write to read-only reg 0x{offset:X}")
        raise BusError(f"INTC: invalid offset 0x{offset:X}")
