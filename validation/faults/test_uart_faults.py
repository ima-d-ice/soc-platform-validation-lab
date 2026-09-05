"""UART stuck-busy fault: no false completion, timeout detect, clean recovery."""
from __future__ import annotations

from soc.faults import Fault, FaultInjector, RecoveryTracker

UART_BASE = 0x20000000
TXDATA = UART_BASE + 0x00
RXDATA = UART_BASE + 0x04
STATUS = UART_BASE + 0x08
CTRL = UART_BASE + 0x0C

TX_BUSY = 1 << 0
TX_EMPTY = 1 << 1
RX_VALID = 1 << 2
ENABLE = 1 << 0

IRQ_UART = 0
INTC_PENDING = 0x20003004


def test_uart_stuck_busy_never_completes(soc):
    soc.write(CTRL, ENABLE)
    assert soc.write(TXDATA, 0x41) == 0
    inj = FaultInjector(soc)
    inj.inject(Fault("uart-stuck-busy"))
    assert inj.is_active("uart-stuck-busy")
    lat = soc.config["uart_latency_ticks"]
    soc.step(3 * lat)  # far beyond healthy completion
    st = soc.read(STATUS)
    assert st & TX_BUSY  # still busy
    assert not (st & RX_VALID)  # no false completion
    assert not (st & TX_EMPTY)
    assert not (soc.read(INTC_PENDING) & (1 << IRQ_UART))  # no completion IRQ


def test_uart_stuck_detected_and_recovered(soc):
    lat = soc.config["uart_latency_ticks"]
    budget = 4 * lat
    soc.write(CTRL, ENABLE)
    assert soc.write(TXDATA, 0x42) == 0
    inj = FaultInjector(soc)
    tracker = RecoveryTracker()
    t_inject = soc.ticks
    inj.inject(Fault("uart-stuck-busy"))
    tracker.on_fault(t_inject, "uart-stuck-busy")
    elapsed = 0
    while elapsed < budget:
        if soc.read(STATUS) & RX_VALID:
            break
        soc.step(1)
        elapsed += 1
    assert not (soc.read(STATUS) & RX_VALID)  # budget expired: fault confirmed
    t_detect = soc.ticks
    tracker.on_detected(t_detect)
    assert tracker.detection_latency == budget
    # Recovery: clear latch (no watchdog register exists; validation timeout
    # recovery uses the existing STATUS behavior).
    tracker.on_recovery_start()
    inj.clear("uart-stuck-busy")
    soc.run_until(lambda: bool(soc.read(STATUS) & RX_VALID), max_ticks=4 * lat)
    tracker.on_recovered(soc.ticks)
    assert tracker.final_state == "RECOVERED"
    st = soc.read(STATUS)
    assert st & TX_EMPTY
    assert st & RX_VALID
    assert soc.read(RXDATA) == 0x42  # original byte delivered, not corrupted
    assert not (soc.read(STATUS) & RX_VALID)  # read clears per contract


def test_uart_stuck_repeat_is_identical(config):
    from soc.soc import SoC

    def once():
        s = SoC(config)
        s.boot()
        lat = config["uart_latency_ticks"]
        s.write(CTRL, ENABLE)
        s.write(TXDATA, 0x43)
        inj = FaultInjector(s)
        inj.inject(Fault("uart-stuck-busy"))
        t0 = s.ticks
        s.step(3 * lat)
        st = s.read(STATUS)
        inj.clear("uart-stuck-busy")
        s.run_until(lambda: bool(s.read(STATUS) & RX_VALID), max_ticks=4 * lat)
        return (s.ticks - t0, st, s.read(RXDATA))

    assert once() == once()
