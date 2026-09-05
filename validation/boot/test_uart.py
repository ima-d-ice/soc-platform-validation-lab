"""UART validation: init, loopback, disabled-TX, busy timing."""
from __future__ import annotations

UART_BASE = 0x20000000
TXDATA = UART_BASE + 0x00
RXDATA = UART_BASE + 0x04
STATUS = UART_BASE + 0x08
CTRL = UART_BASE + 0x0C
BAUDDIV = UART_BASE + 0x10

TX_BUSY = 1 << 0
TX_EMPTY = 1 << 1
RX_VALID = 1 << 2
ENABLE = 1 << 0


def test_uart_initializes(soc):
    soc.write(BAUDDIV, 0)
    soc.write(CTRL, ENABLE)
    assert soc.read(CTRL) == ENABLE
    st = soc.read(STATUS)
    assert st & TX_EMPTY
    assert not (st & TX_BUSY)


def test_uart_loopback(soc):
    soc.write(CTRL, ENABLE)
    rc = soc.write(TXDATA, ord("A"))
    assert rc == 0
    # Busy immediately after TX.
    assert soc.read(STATUS) & TX_BUSY
    latency = soc.config["uart_latency_ticks"]
    soc.step(latency)
    st = soc.read(STATUS)
    assert st & RX_VALID
    assert st & TX_EMPTY
    assert soc.read(RXDATA) == ord("A")
    # Reading RXDATA clears RX_VALID (contract).
    assert not (soc.read(STATUS) & RX_VALID)


def test_uart_tx_while_disabled_rejected(soc):
    soc.write(CTRL, 0)  # ensure disabled (reset value)
    rc = soc.write(TXDATA, ord("X"))
    assert rc == -1  # UART_ERR_DISABLED
    soc.step(soc.config["uart_latency_ticks"])
    assert not (soc.read(STATUS) & RX_VALID)


def test_uart_busy_timing(soc):
    latency = int(soc.config["uart_latency_ticks"])
    soc.write(CTRL, ENABLE)
    soc.write(TXDATA, 0x55)
    # After latency-1 ticks still busy; after latency ticks idle.
    soc.step(latency - 1)
    assert soc.read(STATUS) & TX_BUSY
    soc.step(1)
    assert soc.read(STATUS) & TX_EMPTY
    assert soc.read(STATUS) & RX_VALID
