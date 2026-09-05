"""Peripheral-reset faults: mid-activity reset restores documented reset
values deterministically; software re-inits and resumes. The existing
reset_peripherals() contract is unchanged (asserted, not extended)."""
from __future__ import annotations

UART_BASE = 0x20000000
U_TXDATA = UART_BASE + 0x00
U_STATUS = UART_BASE + 0x08
U_CTRL = UART_BASE + 0x0C

TIMER_BASE = 0x20001000
T_CTRL = TIMER_BASE + 0x00
T_LOAD = TIMER_BASE + 0x04
T_VALUE = TIMER_BASE + 0x08
T_IRQ_STATUS = TIMER_BASE + 0x0C

DMA_BASE = 0x20002000
D_SRC = DMA_BASE + 0x00
D_DST = DMA_BASE + 0x04
D_LEN = DMA_BASE + 0x08
D_CTRL = DMA_BASE + 0x0C
D_STATUS = DMA_BASE + 0x10
D_ERR = DMA_BASE + 0x18

INTC_BASE = 0x20003000
INTC_ENABLE = INTC_BASE + 0x00
INTC_PENDING = INTC_BASE + 0x04
INTC_ACK = INTC_BASE + 0x08
INTC_CLEAR = INTC_BASE + 0x0C
INTC_ACTIVE = INTC_BASE + 0x10

SRAM_BASE = 0x10000000
IRQ_TIMER, IRQ_DMA = 1, 2
BUSY, DONE = 1 << 0, 1 << 1


def test_timer_reset_while_irq_pending(soc):
    soc.write(INTC_ENABLE, 1 << IRQ_TIMER)
    soc.write(T_LOAD, 4)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.run_until(lambda: soc.read(T_IRQ_STATUS) & 0x1, max_ticks=50)
    assert soc.read(INTC_PENDING) & (1 << IRQ_TIMER)
    # Fault: reset lands mid-activity.
    soc.reset_peripherals()
    # Documented reset values restored (spec §2).
    assert soc.read(T_CTRL) == 0
    assert soc.read(T_LOAD) == 0
    assert soc.read(T_VALUE) == 0
    assert soc.read(T_IRQ_STATUS) == 0
    assert soc.read(U_CTRL) == 0
    assert soc.read(D_STATUS) == 0
    assert soc.read(D_ERR) == 0
    assert soc.read(INTC_ENABLE) == 0
    assert soc.read(INTC_PENDING) == 0
    assert soc.read(INTC_ACTIVE) == 0
    # Software detects (no pending where one was) and recovers by re-init.
    assert soc.read(INTC_PENDING) == 0
    soc.write(INTC_ENABLE, 1 << IRQ_TIMER)
    soc.write(T_LOAD, 4)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.run_until(lambda: soc.read(T_IRQ_STATUS) & 0x1, max_ticks=50)
    assert soc.read(INTC_PENDING) & (1 << IRQ_TIMER)
    assert soc.read(INTC_ACK) == IRQ_TIMER
    soc.write(INTC_CLEAR, IRQ_TIMER)


def test_reset_during_dma_discards_and_recovers(soc):
    nbytes = 1024
    for i in range(nbytes // 4):
        soc.sram_write_word(SRAM_BASE + i * 4, 0xD0000000 | i)
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1)
    assert soc.read(D_STATUS) & BUSY
    soc.step(nbytes // 8)  # mid-transfer
    assert soc.read(D_STATUS) & BUSY
    # Fault: peripheral reset during activity.
    soc.reset_peripherals()
    assert soc.read(D_STATUS) == 0  # idle: BUSY/DONE/ERROR all cleared
    assert soc.read(D_ERR) == 0
    assert soc.read(INTC_PENDING) == 0
    # Software re-runs the whole transfer and it completes byte-correct.
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1)
    soc.run_until(lambda: soc.read(D_STATUS) & DONE, max_ticks=5000)
    for i in range(nbytes // 4):
        assert soc.sram_read_word(SRAM_BASE + 0x1000 + i * 4) == (0xD0000000 | i)


def test_reset_contract_unchanged(soc):
    # reset_peripherals() clears exactly the documented state, nothing else.
    soc.sram_write_word(SRAM_BASE, 0x12345678)
    soc.write(U_CTRL, 0x1)
    soc.write(INTC_ENABLE, 0x7)
    soc.reset_peripherals()
    assert soc.sram_read_word(SRAM_BASE) == 0x12345678  # SRAM preserved
    assert soc.read(U_CTRL) == 0
    assert soc.read(U_STATUS) == 0x2  # TX_EMPTY reset value
    assert soc.read(INTC_ENABLE) == 0
    assert soc.ticks >= 5  # boot ticks retained; reset is not a reboot
