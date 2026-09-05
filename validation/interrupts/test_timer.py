"""Timer + INTC validation (MVP: single-line arrival, ack, clear, gating).

Priority/nesting across concurrent sources is deferred.
"""
from __future__ import annotations

TIMER_BASE = 0x20001000
CTRL = TIMER_BASE + 0x00
LOAD = TIMER_BASE + 0x04
VALUE = TIMER_BASE + 0x08
IRQ_STATUS = TIMER_BASE + 0x0C
IRQ_CLEAR = TIMER_BASE + 0x10

INTC_BASE = 0x20003000
ENABLE = INTC_BASE + 0x00
PENDING = INTC_BASE + 0x04
ACK = INTC_BASE + 0x08
CLEAR = INTC_BASE + 0x0C
ACTIVE = INTC_BASE + 0x10

IRQ_TIMER = 1
IRQ_NONE = 0xFFFFFFFF

T_ENABLE = 1 << 0
T_PERIODIC = 1 << 1
T_IRQ_EN = 1 << 2


def test_timer_fires_oneshot(soc):
    soc.write(ENABLE, 1 << IRQ_TIMER)
    soc.write(LOAD, 10)
    soc.write(CTRL, T_ENABLE | T_IRQ_EN)
    soc.run_until(lambda: soc.read(IRQ_STATUS) & 0x1, max_ticks=50)
    assert soc.read(VALUE) == 0
    assert soc.read(PENDING) & (1 << IRQ_TIMER)
    acked = soc.read(ACK)
    assert acked == IRQ_TIMER
    assert soc.read(ACTIVE) & (1 << IRQ_TIMER)
    # One-shot auto-disables.
    assert not (soc.read(CTRL) & T_ENABLE)
    soc.write(CLEAR, IRQ_TIMER)
    assert not (soc.read(ACTIVE) & (1 << IRQ_TIMER))
    # W1C clear of peripheral flag.
    soc.write(IRQ_STATUS, 0x1)
    assert not (soc.read(IRQ_STATUS) & 0x1)


def test_timer_periodic_reloads(soc):
    soc.write(ENABLE, 1 << IRQ_TIMER)
    soc.write(LOAD, 5)
    soc.write(CTRL, T_ENABLE | T_PERIODIC | T_IRQ_EN)
    for _ in range(2):
        soc.run_until(lambda: soc.read(IRQ_STATUS) & 0x1, max_ticks=20)
        assert soc.read(ACK) == IRQ_TIMER
        soc.write(CLEAR, IRQ_TIMER)
        soc.write(IRQ_CLEAR, 0x1)
    # Still enabled for periodic.
    assert soc.read(CTRL) & T_ENABLE


def test_timer_load_zero_never_fires(soc):
    soc.write(ENABLE, 1 << IRQ_TIMER)
    soc.write(LOAD, 0)
    soc.write(CTRL, T_ENABLE | T_IRQ_EN)
    soc.step(20)
    assert not (soc.read(IRQ_STATUS) & 0x1)
    assert not (soc.read(PENDING) & (1 << IRQ_TIMER))
    assert soc.read(ACK) == IRQ_NONE
