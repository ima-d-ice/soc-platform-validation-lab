"""INTC priority + storm + determinism (v0.2, complete controller).

Fixed order: TIMER(1) > DMA(2) > UART(0). Non-preemptive, queued.
All sources are real peripherals: TIMER countdown, DMA completion, UART
RX completion. Nothing is manually forced into PENDING.
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

IRQ_UART = 0
IRQ_TIMER = 1
IRQ_DMA = 2
IRQ_NONE = 0xFFFFFFFF


def _raise_all_three(soc):
    """Trigger TIMER + DMA + UART so all three are pending together."""
    soc.write(ENABLE, 0x7)
    # TIMER fires in 5 ticks.
    soc.write(T_LOAD, 5)
    soc.write(T_CTRL, 0x1 | 0x4)
    # DMA 16B completes in 4 ticks (single-transfer timing, pre-burst).
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, 16)
    soc.write(D_CTRL, 0x1 | 0x2)
    # UART completes in uart_latency_ticks (5 on base config).
    soc.write(U_CTRL, 0x1)
    soc.write(U_TXDATA, 0x41)
    soc.run_until(lambda: soc.read(PENDING) == 0x7, max_ticks=50)


def test_three_way_priority_order(soc):
    _raise_all_three(soc)
    assert soc.read(PENDING) == 0x7
    order = []
    for _ in range(3):
        acked = soc.read(ACK)
        order.append(acked)
        soc.write(CLEAR, acked)
    assert order == [IRQ_TIMER, IRQ_DMA, IRQ_UART]
    assert soc.read(ACK) == IRQ_NONE


def test_gating_selects_among_pending(soc):
    _raise_all_three(soc)
    # Only UART enabled: highest *enabled* pending wins.
    soc.write(ENABLE, 1 << IRQ_UART)
    assert soc.read(ACK) == IRQ_UART
    soc.write(CLEAR, IRQ_UART)
    assert soc.read(ACK) == IRQ_NONE  # timer/dma pending but gated
    soc.write(ENABLE, 0x7)
    assert soc.read(ACK) == IRQ_TIMER


def test_storm_coalesces(soc):
    soc.write(ENABLE, 1 << IRQ_TIMER)
    soc.write(T_LOAD, 2)
    soc.write(T_CTRL, 0x1 | 0x2 | 0x4)  # ENABLE|PERIODIC|IRQ_ENABLE
    soc.step(10)  # several periods fire before any ACK
    assert soc.read(PENDING) & (1 << IRQ_TIMER)
    before = soc.read(PERF_IRQ)
    assert soc.read(ACK) == IRQ_TIMER
    assert soc.read(PERF_IRQ) == before + 1  # coalesced: one ACK, not N
    soc.write(CLEAR, IRQ_TIMER)


def test_irq_count_exact_and_deterministic(soc):
    _raise_all_three(soc)
    before = soc.read(PERF_IRQ)
    seq = []
    for _ in range(3):
        a = soc.read(ACK)
        seq.append(a)
        soc.write(CLEAR, a)
    assert soc.read(PERF_IRQ) == before + 3
    # Repeat the whole sequence: identical order (deterministic).
    _raise_all_three(soc)
    seq2 = []
    for _ in range(3):
        a = soc.read(ACK)
        seq2.append(a)
        soc.write(CLEAR, a)
    assert seq2 == seq == [IRQ_TIMER, IRQ_DMA, IRQ_UART]
