"""Linux platform validation: init, registers, integrity, buffers, completion."""
from __future__ import annotations

import pytest

from linux.app import StreamApp
from linux.driver import StreamDriver, StreamError
from linux.mmio import DeviceRegs
from soc.bus import BusError


def _drv(soc, *, depth=4, irq=False):
    d = StreamDriver(soc, ring_depth=depth)
    d.init(irq_mode=irq)
    return d


def test_initialization(soc):
    d = StreamDriver(soc, ring_depth=2)
    with pytest.raises(StreamError):
        d.alloc(64)  # not initialized
    d.init(irq_mode=False)
    assert soc.read(0x20002010) == 0  # DMA STATUS idle
    assert soc.read(0x20003000) == 0  # INTC gating off
    d.init(irq_mode=True)
    assert soc.read(0x20003000) == (1 << 2)  # DMA line enabled
    d.close()
    assert soc.read(0x20003000) == 0


def test_register_access(soc):
    d = _drv(soc)
    regs = DeviceRegs(soc)
    regs.dma_program(0x10000000, 0x10001000, 64, False)
    assert regs.read(0x20002000) == 0x10000000  # SRC readback
    assert regs.read(0x20002008) == 64  # LEN readback
    assert regs.dma_status() & 0x1  # BUSY
    d.close()


def test_data_integrity_both_modes(soc):
    for irq in (False, True):
        from soc.soc import SoC
        s = SoC(soc.config)
        s.boot()
        d = _drv(s, irq=irq)
        for size in (64, 1024):
            h = d.alloc(size)
            t = d.submit(h, size, 0xE0000000 | size, timeout=100)
            d.wait(t, timeout=5000)
            assert d.verify(t)
        d.close()


def test_buffer_management(soc):
    d = _drv(soc)
    h1 = d.alloc(64)
    h2 = d.alloc(64)
    assert h1 != h2  # opaque handles distinct
    with pytest.raises(StreamError):
        d.alloc(0)
    with pytest.raises(StreamError):
        d.alloc(3)  # unaligned size
    with pytest.raises(StreamError):
        d.submit(9999, 64, 0)  # unknown buffer
    # Arena exhaustion is a clean error, not a crash.
    with pytest.raises(StreamError):
        d.alloc(0x8000)
    d.close()


def test_completion_notification_vs_poll(soc):
    from soc.soc import SoC
    s1 = SoC(soc.config)
    s1.boot()
    d1 = _drv(s1, irq=False)
    h1 = d1.alloc(256)
    t1 = d1.submit(h1, 256, 0x11, timeout=100)
    d1.wait(t1, timeout=5000)
    assert d1.notifications == 0
    assert d1.poll_reads > 0

    s2 = SoC(soc.config)
    s2.boot()
    d2 = _drv(s2, irq=True)
    h2 = d2.alloc(256)
    t2 = d2.submit(h2, 256, 0x11, timeout=100)
    d2.wait(t2, timeout=5000)
    assert d2.notifications == 1
    assert d2.poll_reads == 0
    # Same transfer ticks both modes (no speed claim either way).
    assert (t1.frame.t_complete - t1.frame.t_start) == (
        t2.frame.t_complete - t2.frame.t_start)
    d1.close()
    d2.close()


def test_timeout_handling(soc):
    from soc.faults import Fault, FaultInjector
    d = _drv(soc, irq=False)
    h = d.alloc(64)
    inj = FaultInjector(soc)
    t = d.submit(h, 64, 0x22, timeout=100)
    inj.inject(Fault("dma-timeout"))  # engine freezes mid-transfer
    with pytest.raises(StreamError, match="completion timeout"):
        d.wait(t, timeout=50)
    assert d.timeouts == 1
    d.abort()  # deterministic recovery to idle
    assert soc.read(0x20002010) == 0
    inj.clear("dma-timeout")
    d.close()


def test_invalid_access(soc):
    d = _drv(soc)
    h = d.alloc(64)
    # Bad DMA address surfaces as a driver error, engine left clean.
    with pytest.raises(StreamError):
        t = d.submit(h, 64, 0x33, timeout=100)
        soc.write(0x20002000, 0x30000000)  # corrupt SRC post-submit
        d.wait(t, timeout=5000)
    d.abort()
    # Raw illegal MMIO still raises BusError through the MMIO layer.
    with pytest.raises(BusError):
        soc.read(0x30000000)
    d.close()


def test_app_pipeline_deterministic(config):
    from soc.soc import SoC

    def once():
        s = SoC(config)
        s.boot()
        d = StreamDriver(s, ring_depth=2)
        d.init(irq_mode=True)
        bufs = [d.alloc(256) for _ in range(2)]
        app = StreamApp(d, consumer_period=30)
        out = app.run([(bufs[i % 2], 256, 0xC0000000 + i) for i in range(8)])
        d.close()
        return (out["submitted"], out["completed"], out["mismatches"],
                tuple(out["latencies"]), out["notifications"])

    a, b = once(), once()
    assert a == b
    assert a[2] == 0 and a[3] and a[4] == 8
