"""DMA fault validation: invalid address, timeout/stuck-busy, sticky + two-step clear."""
from __future__ import annotations

from soc.faults import Fault, FaultInjector, RecoveryTracker

SRAM_BASE = 0x10000000
DMA_BASE = 0x20002000
SRC = DMA_BASE + 0x00
DST = DMA_BASE + 0x04
LEN = DMA_BASE + 0x08
CTRL = DMA_BASE + 0x0C
STATUS = DMA_BASE + 0x10
IRQ_CLEAR = DMA_BASE + 0x14
ERR_CODE = DMA_BASE + 0x18

INTC_BASE = 0x20003000
INTC_ENABLE = INTC_BASE + 0x00
INTC_PENDING = INTC_BASE + 0x04
INTC_ACK = INTC_BASE + 0x08
INTC_CLEAR = INTC_BASE + 0x0C
INTC_ACTIVE = INTC_BASE + 0x10

IRQ_DMA = 2
IRQ_NONE = 0xFFFFFFFF
BUSY = 1 << 0
DONE = 1 << 1
ERROR = 1 << 2

GUARD = SRAM_BASE + 0x3000
GUARD_VAL = 0x5AFE5AFE


def _expected_ticks(nbytes: int, burst: int, lat: int) -> int:
    import math

    words = math.ceil(nbytes / 4)
    bursts = math.ceil(words / burst)
    return max(1, words * lat + (bursts - 1))


def _start(soc, src, dst, nbytes, irq_en=True):
    soc.write(SRC, src)
    soc.write(DST, dst)
    soc.write(LEN, nbytes)
    soc.write(CTRL, 0x1 | (0x2 if irq_en else 0))


def test_invalid_src_reaches_error_without_corruption(soc):
    soc.sram_write_word(GUARD, GUARD_VAL)
    for i in range(4):
        soc.sram_write_word(SRAM_BASE + 0x1000 + i * 4, 0xAAAAAAAA)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    _start(soc, 0x30000000, SRAM_BASE + 0x1000, 16, irq_en=True)
    soc.step(2)
    assert soc.read(STATUS) & ERROR  # deterministic ERROR, no BUSY phase
    assert not (soc.read(STATUS) & BUSY)
    assert not (soc.read(STATUS) & DONE)
    assert soc.read(ERR_CODE) == 1
    assert soc.read(GUARD) == GUARD_VAL  # nothing touched
    for i in range(4):
        assert soc.sram_read_word(SRAM_BASE + 0x1000 + i * 4) == 0xAAAAAAAA
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)  # IRQ iff enabled


def test_invalid_dst_reaches_error_deterministically(soc):
    _start(soc, SRAM_BASE, 0x40000000, 16, irq_en=False)
    soc.step(2)
    assert soc.read(STATUS) & ERROR
    assert soc.read(ERR_CODE) == 1
    assert not (soc.read(INTC_PENDING) & (1 << IRQ_DMA))  # IRQ gated by enable
    # Repeat identically.
    soc.write(IRQ_CLEAR, 1)
    _start(soc, SRAM_BASE, 0x40000000, 16, irq_en=False)
    soc.step(2)
    assert soc.read(STATUS) & ERROR
    assert soc.read(ERR_CODE) == 1


def test_error_sticky_and_two_steps_distinct(soc):
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    _start(soc, 0x30000000, SRAM_BASE, 16, irq_en=True)
    soc.step(2)
    soc.step(10)
    assert soc.read(STATUS) & ERROR  # sticky across idle ticks
    # Step 1: DMA flag clear does NOT clear INTC pending.
    soc.write(IRQ_CLEAR, 1)
    assert not (soc.read(STATUS) & ERROR)
    assert soc.read(ERR_CODE) == 0
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    # Step 2: ACK moves pending->active; INTC_CLEAR finishes.
    assert soc.read(INTC_ACK) == IRQ_DMA
    assert soc.read(INTC_ACTIVE) & (1 << IRQ_DMA)
    soc.write(INTC_CLEAR, IRQ_DMA)
    assert not (soc.read(INTC_ACTIVE) & (1 << IRQ_DMA))
    assert soc.read(INTC_ACK) == IRQ_NONE


def test_dma_timeout_detected_and_recovered(soc):
    nbytes, burst = 64, soc.config["dma_burst"]
    lat = soc.config["dma_latency_per_word_ticks"]
    expected = _expected_ticks(nbytes, burst, lat)
    budget = 4 * expected
    inj = FaultInjector(soc)
    tracker = RecoveryTracker()
    _start(soc, SRAM_BASE, SRAM_BASE + 0x1000, nbytes, irq_en=True)
    assert soc.read(STATUS) & BUSY
    t_inject = soc.ticks
    inj.inject(Fault("dma-timeout"))
    tracker.on_fault(t_inject, "dma-timeout")
    # Stuck: no completion no matter how long the healthy transfer takes.
    soc.step(2 * expected)
    assert soc.read(STATUS) & BUSY
    assert not (soc.read(STATUS) & DONE)
    # Validation-side timeout budget expires -> detected.
    elapsed = 0
    while elapsed < budget:
        if not (soc.read(STATUS) & BUSY):
            break
        soc.step(1)
        elapsed += 1
    assert soc.read(STATUS) & BUSY  # still stuck: timeout confirmed
    t_detect = soc.ticks
    tracker.on_detected(t_detect)
    assert tracker.detection_latency == t_detect - t_inject
    # Recovery: abort, re-init, two-step clear, verify idle.
    tracker.on_recovery_start()
    inj.clear("dma-timeout")
    soc.dma.reset()
    soc.write(IRQ_CLEAR, 1)
    soc.write(INTC_CLEAR, IRQ_DMA)
    assert soc.read(STATUS) == 0
    assert not (soc.read(INTC_PENDING) & (1 << IRQ_DMA))
    tracker.on_recovered(soc.ticks)
    assert tracker.final_state == "RECOVERED"
    # Post-recovery the engine is healthy: clean transfer completes.
    for i in range(nbytes // 4):
        soc.sram_write_word(SRAM_BASE + i * 4, 0xC0000000 | i)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    _start(soc, SRAM_BASE, SRAM_BASE + 0x1000, nbytes, irq_en=True)
    soc.run_until(lambda: soc.read(STATUS) & (DONE | ERROR), max_ticks=1000)
    assert soc.read(STATUS) & DONE
    assert soc.read(INTC_ACK) == IRQ_DMA
    soc.write(INTC_CLEAR, IRQ_DMA)
    soc.write(IRQ_CLEAR, 1)
    for i in range(nbytes // 4):
        assert soc.sram_read_word(SRAM_BASE + 0x1000 + i * 4) == (0xC0000000 | i)


def test_dma_timeout_repeat_is_identical(config):
    from soc.soc import SoC

    def once():
        s = SoC(config)
        s.boot()
        burst, lat = config["dma_burst"], config["dma_latency_per_word_ticks"]
        expected = _expected_ticks(64, burst, lat)
        inj = FaultInjector(s)
        _start(s, SRAM_BASE, SRAM_BASE + 0x1000, 64, irq_en=True)
        inj.inject(Fault("dma-timeout"))
        t0 = s.ticks
        s.step(2 * expected)
        el = 0
        while el < 4 * expected:
            if not (s.read(STATUS) & BUSY):
                break
            s.step(1)
            el += 1
        return (s.ticks - t0, el, s.read(STATUS), s.perf.stalls)

    assert once() == once()


def test_injector_schedule_at_tick_and_event(soc):
    inj = FaultInjector(soc)
    inj.apply_at_tick(Fault("dma-timeout"), soc.ticks + 3)
    assert not inj.is_active("dma-timeout")
    for _ in range(5):
        soc.step(1)
        inj.poll()
    assert inj.is_active("dma-timeout")
    assert soc.dma.fault_stuck_busy is True
    inj.clear("dma-timeout")
    assert not inj.is_active("dma-timeout")
    assert soc.dma.fault_stuck_busy is False
    # Event-based: fires when DMA becomes BUSY.
    inj.apply_at_event(Fault("dma-timeout"), lambda s: bool(s.read(STATUS) & BUSY))
    _start(soc, SRAM_BASE, SRAM_BASE + 0x1000, 64, irq_en=False)
    inj.poll()
    assert inj.is_active("dma-timeout")
    inj.clear("dma-timeout")
    assert not inj.is_active("dma-timeout")
    assert soc.dma.fault_stuck_busy is False
