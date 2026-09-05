"""UART loopback model with busy latency + RX completion IRQ (line 0).

IRQ policy (v0.2): when a TX completes (busy expires, RX_VALID set), raise
INTC line 0 unconditionally. Delivery is gated solely by INTC.ENABLE —
there is no per-UART IRQ-enable bit, preserving the register map.
"""
from __future__ import annotations

from .bus import BusError

TXDATA_OFF = 0x00
RXDATA_OFF = 0x04
STATUS_OFF = 0x08
CTRL_OFF = 0x0C
BAUDDIV_OFF = 0x10

STATUS_TX_BUSY = 1 << 0
STATUS_TX_EMPTY = 1 << 1
STATUS_RX_VALID = 1 << 2
CTRL_ENABLE = 1 << 0

UART_ERR_DISABLED = -1

IRQ_LINE = 0


class Uart:
    def __init__(self, *, latency_ticks: int = 5, perf=None, intc=None):
        self.latency_ticks = latency_ticks
        self._perf = perf
        self._intc = intc
        self.ctrl = 0
        self.bauddiv = 0
        self._txdata = 0
        self._rxdata = 0
        self._busy = 0  # ticks remaining
        self._rx_valid = False
        # Fault hook (Phase 5): when True, the busy countdown never advances
        # (stuck-busy). Default off; reset clears it. No register change.
        self.fault_stuck_busy = False

    def reset(self) -> None:
        self.ctrl = 0
        self.bauddiv = 0
        self._txdata = 0
        self._rxdata = 0
        self._busy = 0
        self._rx_valid = False
        self.fault_stuck_busy = False

    def _status(self) -> int:
        s = 0
        if self._busy > 0:
            s |= STATUS_TX_BUSY
        else:
            s |= STATUS_TX_EMPTY
        if self._rx_valid:
            s |= STATUS_RX_VALID
        return s

    def read(self, offset: int) -> int:
        if offset == TXDATA_OFF:
            raise BusError("UART: read from write-only TXDATA")
        if offset == RXDATA_OFF:
            val = self._rxdata & 0xFF
            self._rx_valid = False
            return val
        if offset == STATUS_OFF:
            return self._status()
        if offset == CTRL_OFF:
            return self.ctrl & 0xFFFFFFFF
        if offset == BAUDDIV_OFF:
            return self.bauddiv & 0xFFFFFFFF
        raise BusError(f"UART: invalid offset 0x{offset:X}")

    def write(self, offset: int, value: int) -> int:
        """Returns 0 on success, UART_ERR_DISABLED if TX while disabled."""
        value &= 0xFFFFFFFF
        if offset == TXDATA_OFF:
            if not (self.ctrl & CTRL_ENABLE):
                if self._perf is not None:
                    self._perf.count_stall()
                return UART_ERR_DISABLED
            self._txdata = value & 0xFF
            self._busy = max(1, self.latency_ticks)
            return 0
        if offset == CTRL_OFF:
            self.ctrl = value
            return 0
        if offset == BAUDDIV_OFF:
            self.bauddiv = value
            return 0
        if offset in (RXDATA_OFF, STATUS_OFF):
            raise BusError(f"UART: write to read-only reg 0x{offset:X}")
        raise BusError(f"UART: invalid offset 0x{offset:X}")

    def step(self) -> None:
        if self._busy > 0:
            if self.fault_stuck_busy:
                return  # stuck-busy fault: stays BUSY, never completes
            self._busy -= 1
            if self._busy == 0:
                self._rxdata = self._txdata
                self._rx_valid = True
                if self._intc is not None:
                    self._intc.raise_irq(IRQ_LINE)
