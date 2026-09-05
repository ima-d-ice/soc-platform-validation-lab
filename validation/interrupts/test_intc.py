"""INTC validation: gating, ack->active->clear, spurious ack."""
from __future__ import annotations

INTC_BASE = 0x20003000
ENABLE = INTC_BASE + 0x00
PENDING = INTC_BASE + 0x04
ACK = INTC_BASE + 0x08
CLEAR = INTC_BASE + 0x0C
ACTIVE = INTC_BASE + 0x10

TIMER_BASE = 0x20001000
T_CTRL = TIMER_BASE + 0x00
T_LOAD = TIMER_BASE + 0x04
T_IRQ_STATUS = TIMER_BASE + 0x0C
T_IRQ_CLEAR = TIMER_BASE + 0x10

IRQ_TIMER = 1
IRQ_NONE = 0xFFFFFFFF


def _fire_timer(soc, load: int = 4):
    soc.write(T_LOAD, load)
    soc.write(T_CTRL, 0x1 | 0x4)  # ENABLE | IRQ_ENABLE
    soc.run_until(lambda: soc.read(T_IRQ_STATUS) & 0x1, max_ticks=50)


def test_enable_gating(soc):
    soc.write(ENABLE, 0)  # nothing enabled
    _fire_timer(soc)
    assert soc.read(PENDING) & (1 << IRQ_TIMER)
    assert soc.read(ACK) == IRQ_NONE  # gated: no ack without enable
    soc.write(ENABLE, 1 << IRQ_TIMER)
    assert soc.read(ACK) == IRQ_TIMER


def test_ack_moves_pending_to_active(soc):
    soc.write(ENABLE, 1 << IRQ_TIMER)
    _fire_timer(soc)
    assert soc.read(ACK) == IRQ_TIMER
    assert not (soc.read(PENDING) & (1 << IRQ_TIMER))
    assert soc.read(ACTIVE) & (1 << IRQ_TIMER)
    soc.write(CLEAR, IRQ_TIMER)
    assert not (soc.read(ACTIVE) & (1 << IRQ_TIMER))


def test_spurious_ack_returns_none(soc):
    soc.write(ENABLE, 0x7)
    before = soc.read(0x2000400C)  # PERF IRQ_COUNT
    assert soc.read(ACK) == IRQ_NONE
    after = soc.read(0x2000400C)
    assert after == before  # spurious ack counts nothing
