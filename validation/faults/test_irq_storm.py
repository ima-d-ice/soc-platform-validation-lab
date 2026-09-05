"""Interrupt-storm validation: coalescing, exact IRQ counts, stable priority.

No nested/preemptive behavior is introduced; storms queue per the
documented non-preemptive semantics (priority TIMER > DMA > UART).
"""
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

UART_BASE = 0x20000000
U_TXDATA = UART_BASE + 0x00
U_CTRL = UART_BASE + 0x0C

DMA_BASE = 0x20002000
D_SRC = DMA_BASE + 0x00
D_DST = DMA_BASE + 0x04
D_LEN = DMA_BASE + 0x08
D_CTRL = DMA_BASE + 0x0C
D_STATUS = DMA_BASE + 0x10
D_IRQ_CLEAR = DMA_BASE + 0x14

SRAM_BASE = 0x10000000
PERF_IRQ = 0x2000400C

IRQ_UART, IRQ_TIMER, IRQ_DMA = 0, 1, 2
IRQ_NONE = 0xFFFFFFFF
DONE = 1 << 1


def test_timer_storm_coalesces_to_single_ack(soc):
    soc.write(ENABLE, 1 << IRQ_TIMER)
    soc.write(T_LOAD, 2)
    soc.write(T_CTRL, 0x1 | 0x2 | 0x4)  # ENABLE|PERIODIC|IRQ_ENABLE
    soc.step(20)  # ~10 periods fire before any ACK
    assert soc.read(PENDING) == (1 << IRQ_TIMER)  # coalesced to one bit
    before = soc.read(PERF_IRQ)
    assert soc.read(ACK) == IRQ_TIMER  # no duplicate logical ACKs
    assert soc.read(PERF_IRQ) == before + 1
    assert soc.read(ACK) == IRQ_NONE  # second ACK finds nothing
    assert soc.read(PERF_IRQ) == before + 1
    soc.write(CLEAR, IRQ_TIMER)


def test_mixed_storm_obeys_priority(soc):
    soc.write(ENABLE, 0x7)
    soc.write(T_LOAD, 5)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, 16)
    soc.write(D_CTRL, 0x1 | 0x2)
    soc.write(U_CTRL, 0x1)
    soc.write(U_TXDATA, 0x41)
    soc.run_until(lambda: soc.read(PENDING) == 0x7, max_ticks=50)
    order = []
    for _ in range(3):
        acked = soc.read(ACK)
        order.append(acked)
        # Unrelated pending bits must survive each ACK.
        remaining = 0x7 & ~sum(1 << a for a in order)
        assert soc.read(PENDING) == remaining
        soc.write(CLEAR, acked)
    assert order == [IRQ_TIMER, IRQ_DMA, IRQ_UART]
    assert soc.read(PENDING) == 0
    assert soc.read(ACTIVE) == 0


def test_storm_does_not_clear_unrelated_bits(soc):
    soc.write(ENABLE, 0x7)
    soc.write(T_LOAD, 3)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.write(U_CTRL, 0x1)
    soc.write(U_TXDATA, 0x42)
    soc.run_until(lambda: soc.read(PENDING) == 0x3, max_ticks=50)  # timer+uart
    assert soc.read(ACK) == IRQ_TIMER
    assert soc.read(PENDING) == (1 << IRQ_UART)  # uart bit untouched
    assert soc.read(ACTIVE) == (1 << IRQ_TIMER)
    soc.write(CLEAR, IRQ_TIMER)
    assert soc.read(ACK) == IRQ_UART
    soc.write(CLEAR, IRQ_UART)
    assert soc.read(PENDING) == 0


def test_storm_repeat_is_identical(config):
    from soc.soc import SoC

    def once():
        s = SoC(config)
        s.boot()
        s.write(ENABLE, 0x7)
        s.write(T_LOAD, 2)
        s.write(T_CTRL, 0x1 | 0x2 | 0x4)
        s.step(20)
        pending = s.read(PENDING)
        acked = s.read(ACK)
        irqs = s.read(PERF_IRQ)
        return (pending, acked, irqs)

    assert once() == once()
