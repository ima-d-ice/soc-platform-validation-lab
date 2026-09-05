"""Bus-error validation: invalid register / permission / alignment rejected."""
from __future__ import annotations

import pytest

from soc.bus import BusError

ROM_BASE = 0x00000000
UART_STATUS = 0x20000008  # RO
UART_TXDATA = 0x20000000  # WO
TIMER_VALUE = 0x20001008  # RO
TIMER_IRQ_CLEAR = 0x20001010  # WO
DMA_IRQ_CLEAR = 0x20002014  # WO


def test_invalid_address_rejected(soc):
    with pytest.raises(BusError):
        soc.read(0x30000000)
    with pytest.raises(BusError):
        soc.write(0x30000000, 1)


def test_ro_write_rejected(soc):
    with pytest.raises(BusError):
        soc.write(ROM_BASE, 0x12345678)  # ROM is read-only at run
    with pytest.raises(BusError):
        soc.write(UART_STATUS, 0xFFFF)
    with pytest.raises(BusError):
        soc.write(TIMER_VALUE, 0x1)


def test_wo_read_rejected(soc):
    with pytest.raises(BusError):
        soc.read(UART_TXDATA)
    with pytest.raises(BusError):
        soc.read(TIMER_IRQ_CLEAR)
    with pytest.raises(BusError):
        soc.read(DMA_IRQ_CLEAR)


def test_unaligned_rejected(soc):
    with pytest.raises(BusError):
        soc.read(UART_STATUS + 1)
    with pytest.raises(BusError):
        soc.write(UART_STATUS + 2, 0)
