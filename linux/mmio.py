"""MMIO layer: named register accessors over the virtual SoC bus.

This module is the only place (besides tests) that knows SoC register
addresses. The driver and application layers never import SoC address
constants — buffers are opaque integer handles. BusError from illegal
access propagates unchanged so the driver can translate it.
"""
from __future__ import annotations

from soc.bus import BusError

# Re-exported so driver code reads symbolically; values mirror the SoC map.
DMA_SRC = 0x20002000
DMA_DST = 0x20002004
DMA_LEN = 0x20002008
DMA_CTRL = 0x2000200C
DMA_STATUS = 0x20002010
DMA_IRQ_CLEAR = 0x20002014
DMA_ERR = 0x20002018
CTRL_START = 1 << 0
CTRL_IRQ_EN = 1 << 1
ST_BUSY = 1 << 0
ST_DONE = 1 << 1
ST_ERROR = 1 << 2

INTC_ENABLE = 0x20003000
INTC_PENDING = 0x20003004
INTC_ACK = 0x20003008
INTC_CLEAR = 0x2000300C
IRQ_DMA = 2
IRQ_NONE = 0xFFFFFFFF


class DeviceRegs:
    """Thin MMIO accessor bound to a SoC instance."""

    def __init__(self, soc):
        self._soc = soc

    def read(self, addr: int) -> int:
        return self._soc.read(addr)

    def write(self, addr: int, value: int) -> None:
        self._soc.write(addr, value)

    # DMA engine surface used by the driver.
    def dma_program(self, src: int, dst: int, nbytes: int,
                    irq_en: bool) -> None:
        self.write(DMA_SRC, src)
        self.write(DMA_DST, dst)
        self.write(DMA_LEN, nbytes)
        self.write(DMA_CTRL, CTRL_START | (CTRL_IRQ_EN if irq_en else 0))

    def dma_status(self) -> int:
        return self.read(DMA_STATUS)

    def dma_error(self) -> int:
        return self.read(DMA_ERR)

    def dma_clear(self) -> None:
        self.write(DMA_IRQ_CLEAR, 1)

    def irq_enable_dma(self, on: bool) -> None:
        self.write(INTC_ENABLE, (1 << IRQ_DMA) if on else 0)

    def irq_pending_dma(self) -> bool:
        return bool(self.read(INTC_PENDING) & (1 << IRQ_DMA))

    def irq_ack(self) -> int:
        return self.read(INTC_ACK)

    def irq_clear(self, line: int) -> None:
        self.write(INTC_CLEAR, line)


__all__ = ["BusError", "DeviceRegs"]
