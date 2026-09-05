"""Recovery state-machine validation: legal transitions, ordered
timestamps, derived latencies, repeat determinism. Asserts the behavior
defined by the model — never that recovery must always succeed."""
from __future__ import annotations

import pytest

from soc.faults import (
    FAULT_DETECTED,
    NORMAL,
    RECOVERED,
    RECOVERY,
    UNRECOVERABLE,
    Fault,
    FaultInjector,
    RecoveryTracker,
)

SRAM_BASE = 0x10000000
DMA_BASE = 0x20002000
D_SRC = DMA_BASE + 0x00
D_DST = DMA_BASE + 0x04
D_LEN = DMA_BASE + 0x08
D_CTRL = DMA_BASE + 0x0C
D_STATUS = DMA_BASE + 0x10
D_IRQ_CLEAR = DMA_BASE + 0x14
INTC_CLEAR = 0x2000300C
BUSY, DONE = 1 << 0, 1 << 1


def test_legal_transition_chain():
    t = RecoveryTracker()
    assert t.current_state == NORMAL
    t.on_fault(10, "dma-timeout")
    t.on_detected(20)
    t.on_recovery_start()
    t.on_recovered(30)
    rec = t.record()
    assert rec["current_state"] == RECOVERED
    assert rec["fault_type"] == "dma-timeout"
    assert rec["fault_time"] == 10
    assert rec["detection_time"] == 20
    assert rec["recovery_time"] == 30
    assert rec["final_state"] == RECOVERED
    assert rec["detection_latency_ticks"] == 10  # derived
    assert rec["recovery_latency_ticks"] == 10  # derived


def test_unrecoverable_branch():
    t = RecoveryTracker()
    t.on_fault(5, "mmio-invalid")
    t.on_detected(6)
    t.on_unrecoverable(7)
    assert t.current_state == UNRECOVERABLE
    assert t.final_state == UNRECOVERABLE
    assert t.detection_latency == 1
    assert t.recovery_latency == 1


def test_illegal_transitions_rejected():
    t2 = RecoveryTracker()
    t2.on_fault(1, "x")
    with pytest.raises(AssertionError):
        t2.on_recovered(2)  # must pass through RECOVERY
    t3 = RecoveryTracker()
    t3.on_fault(1, "x")
    t3.on_detected(2)
    t3.on_recovery_start()
    t3.on_recovered(3)
    with pytest.raises(AssertionError):
        t3.on_detected(4)  # terminal state accepts nothing


def test_full_dma_timeout_recovery_tracked(soc):
    inj = FaultInjector(soc)
    tracker = RecoveryTracker()
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, 64)
    soc.write(D_CTRL, 0x1)
    t_fault = soc.ticks
    inj.inject(Fault("dma-timeout"))
    tracker.on_fault(t_fault, "dma-timeout")
    budget = 256
    el = 0
    while el < budget:
        if not (soc.read(D_STATUS) & BUSY):
            break
        soc.step(1)
        el += 1
    assert soc.read(D_STATUS) & BUSY
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    inj.clear("dma-timeout")
    soc.dma.reset()
    soc.write(D_IRQ_CLEAR, 1)
    soc.write(INTC_CLEAR, 2)
    assert soc.read(D_STATUS) == 0
    tracker.on_recovered(soc.ticks)
    rec = tracker.record()
    assert rec["detection_latency_ticks"] == budget
    assert rec["recovery_latency_ticks"] == 0  # abort path is combinational here
    assert rec["final_state"] == RECOVERED


def test_recovery_repeat_is_identical(config):
    from soc.soc import SoC

    def once():
        s = SoC(config)
        s.boot()
        inj = FaultInjector(s)
        tracker = RecoveryTracker()
        s.write(D_SRC, SRAM_BASE)
        s.write(D_DST, SRAM_BASE + 0x1000)
        s.write(D_LEN, 64)
        s.write(D_CTRL, 0x1)
        tracker.on_fault(s.ticks, "dma-timeout")
        inj.inject(Fault("dma-timeout"))
        el = 0
        while el < 256:
            if not (s.read(D_STATUS) & BUSY):
                break
            s.step(1)
            el += 1
        tracker.on_detected(s.ticks)
        tracker.on_recovery_start()
        inj.clear("dma-timeout")
        s.dma.reset()
        tracker.on_recovered(s.ticks)
        return tracker.record()

    a, b = once(), once()
    assert a == b
