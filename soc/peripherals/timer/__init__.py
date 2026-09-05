"""Countdown timer: one-shot / periodic + IRQ."""
from __future__ import annotations

from ...bus import BusError

CTRL_OFF = 0x00
LOAD_OFF = 0x04
VALUE_OFF = 0x08
IRQ_STATUS_OFF = 0x0C
IRQ_CLEAR_OFF = 0x10

CTRL_ENABLE = 1 << 0
CTRL_PERIODIC = 1 << 1
CTRL_IRQ_ENABLE = 1 << 2
IRQ_FIRED = 1 << 0

IRQ_LINE = 1


class Timer:
    def __init__(self, intc=None):
        self._intc = intc
        self.ctrl = 0
        self.load = 0
        self.value = 0
        self.irq_status = 0

    def reset(self) -> None:
        self.ctrl = 0
        self.load = 0
        self.value = 0
        self.irq_status = 0

    def read(self, offset: int) -> int:
        if offset == CTRL_OFF:
            return self.ctrl & 0xFFFFFFFF
        if offset == LOAD_OFF:
            return self.load & 0xFFFFFFFF
        if offset == VALUE_OFF:
            return self.value & 0xFFFFFFFF
        if offset == IRQ_STATUS_OFF:
            return self.irq_status & 0xFFFFFFFF
        if offset == IRQ_CLEAR_OFF:
            raise BusError("TIMER: read from write-only IRQ_CLEAR")
        raise BusError(f"TIMER: invalid offset 0x{offset:X}")

    def write(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if offset == CTRL_OFF:
            was_enabled = bool(self.ctrl & CTRL_ENABLE)
            self.ctrl = value
            now_enabled = bool(self.ctrl & CTRL_ENABLE)
            # On 0->1 enable, latch LOAD into VALUE if VALUE is 0.
            if now_enabled and not was_enabled and self.value == 0:
                self.value = self.load
            return
        if offset == LOAD_OFF:
            self.load = value
            return
        if offset == IRQ_STATUS_OFF:
            # W1C
            if value & IRQ_FIRED:
                self.irq_status &= ~IRQ_FIRED
            return
        if offset == IRQ_CLEAR_OFF:
            if value & IRQ_FIRED:
                self.irq_status &= ~IRQ_FIRED
            return
        if offset == VALUE_OFF:
            raise BusError("TIMER: write to read-only VALUE")
        raise BusError(f"TIMER: invalid offset 0x{offset:X}")

    def step(self) -> None:
        if not (self.ctrl & CTRL_ENABLE):
            return
        if self.load == 0:
            # Defined: LOAD=0 + ENABLE never fires.
            return
        if self.value > 0:
            self.value -= 1
        if self.value == 0:
            self.irq_status |= IRQ_FIRED
            if self.ctrl & CTRL_IRQ_ENABLE and self._intc is not None:
                self._intc.raise_irq(IRQ_LINE)
            if self.ctrl & CTRL_PERIODIC:
                self.value = self.load
            else:
                self.ctrl &= ~CTRL_ENABLE
