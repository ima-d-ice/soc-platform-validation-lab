#!/usr/bin/env python3
"""Fault-injection benchmark (Phase 5): detection/recovery measurements.

Every case starts from a fresh SoC + boot(); no state leaks between runs.
All ticks/counters are read from the virtual SoC timing model (measured);
latencies are subtractions (derived); budgets and wait assumptions are
documented model parameters (modeled). No wall-clock use, no randomness.

Usage:
  python3 benchmarks/fault_injection.py \
    --config configs/base.yaml \
    --faults dma-invalid,dma-timeout,uart-stuck,irq-storm,mmio-invalid \
    --reps 5 \
    --out results/fault_injection.json
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soc.bus import BusError
from soc.faults import Fault, FaultInjector, RecoveryTracker
from soc.soc import SoC, load_config

SRAM_BASE = 0x10000000
UART_BASE = 0x20000000
U_TXDATA = UART_BASE + 0x00
U_RXDATA = UART_BASE + 0x04
U_STATUS = UART_BASE + 0x08
U_CTRL = UART_BASE + 0x0C
TIMER_BASE = 0x20001000
T_CTRL = TIMER_BASE + 0x00
T_LOAD = TIMER_BASE + 0x04
T_IRQ_STATUS = TIMER_BASE + 0x0C
T_IRQ_CLEAR = TIMER_BASE + 0x10
DMA_BASE = 0x20002000
D_SRC = DMA_BASE + 0x00
D_DST = DMA_BASE + 0x04
D_LEN = DMA_BASE + 0x08
D_CTRL = DMA_BASE + 0x0C
D_STATUS = DMA_BASE + 0x10
D_IRQ_CLEAR = DMA_BASE + 0x14
D_ERR = DMA_BASE + 0x18
INTC_BASE = 0x20003000
INTC_ENABLE = INTC_BASE + 0x00
INTC_PENDING = INTC_BASE + 0x04
INTC_ACK = INTC_BASE + 0x08
INTC_CLEAR = INTC_BASE + 0x0C
INTC_ACTIVE = INTC_BASE + 0x10
PERF_IRQ = 0x2000400C
PERF_MEM = 0x20004004
PERF_STALLS = 0x20004010
PERF_DMA_BYTES = 0x20004008

IRQ_UART, IRQ_TIMER, IRQ_DMA = 0, 1, 2
BUSY, DONE, ERROR = 1 << 0, 1 << 1, 1 << 2
RX_VALID = 1 << 2

MEASURED = ["injection_point", "detection_point", "recovery_point",
            "dma_status", "uart_status", "pending_irqs", "active_irq",
            "irq_count", "mem_accesses", "stall_count", "destination_match"]
DERIVED = ["detection_latency_ticks", "recovery_latency_ticks"]
MODELED = ["timeout_budget_ticks"]


def _expected_dma_ticks(nbytes, burst, lat):
    words = math.ceil(nbytes / 4)
    bursts = math.ceil(words / burst)
    return max(1, words * lat + (bursts - 1))


def _snap(soc):
    return {
        "dma_status": soc.read(D_STATUS),
        "uart_status": soc.read(U_STATUS),
        "pending_irqs": soc.read(INTC_PENDING),
        "active_irq": soc.read(INTC_ACTIVE),
        "irq_count": soc.read(PERF_IRQ),
        "mem_accesses": soc.read(PERF_MEM),
        "stall_count": soc.read(PERF_STALLS),
        "dma_bytes_total": soc.read(PERF_DMA_BYTES),
    }


def _dma_start(soc, src, dst, nbytes, irq_en=True):
    soc.write(D_SRC, src)
    soc.write(D_DST, dst)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1 | (0x2 if irq_en else 0))


def _pattern(soc, base, nbytes, tag=0xF0000000):
    for i in range(nbytes // 4):
        soc.sram_write_word(base + i * 4, tag | i)


def _verify(soc, base, nbytes, tag=0xF0000000):
    return all(soc.sram_read_word(base + i * 4) == (tag | i)
               for i in range(nbytes // 4))


def _finish(tracker, snap0, snap1, row):
    row.update({
        "detection_latency_ticks": tracker.detection_latency,
        "recovery_latency_ticks": tracker.recovery_latency,
        "final_state": tracker.final_state,
        "dma_status": snap1["dma_status"],
        "uart_status": snap1["uart_status"],
        "pending_irqs": snap1["pending_irqs"],
        "active_irq": snap1["active_irq"],
        "irq_count": snap1["irq_count"] - snap0["irq_count"],
        "mem_accesses": snap1["mem_accesses"] - snap0["mem_accesses"],
        "stall_count": snap1["stall_count"] - snap0["stall_count"],
        "dma_bytes": snap1["dma_bytes_total"] - snap0["dma_bytes_total"],
        "provenance": {"measured": MEASURED, "derived": DERIVED,
                       "modeled": MODELED},
    })
    return row


def _base_row(fault, rep, budget):
    return {"fault": fault, "rep": rep, "timeout_budget_ticks": budget,
            "destination_match": False}


def case_dma_invalid_src(soc, inj, rep):
    budget = 4  # modeled: synchronous error visible within 4 ticks
    row = _base_row("dma-invalid-src", rep, budget)
    tracker = RecoveryTracker()
    guard = SRAM_BASE + 0x3000
    soc.sram_write_word(guard, 0x5AFE5AFE)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, "dma-invalid-src")
    _dma_start(soc, 0x30000000, SRAM_BASE + 0x1000, 64, irq_en=True)
    t_inject = tracker.fault_time
    soc.step(2)
    assert soc.read(D_STATUS) & ERROR
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    soc.write(D_IRQ_CLEAR, 1)
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    assert soc.read(INTC_ACK) == IRQ_DMA
    soc.write(INTC_CLEAR, IRQ_DMA)
    assert soc.read(D_STATUS) == 0
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": soc.read(guard) == 0x5AFE5AFE
                and soc.read(D_ERR) == 0})
    return _finish(tracker, snap0, _snap(soc) | {"dma_bytes": 0}, row)


def case_dma_invalid_dst(soc, inj, rep):
    budget = 4
    row = _base_row("dma-invalid-dst", rep, budget)
    tracker = RecoveryTracker()
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, "dma-invalid-dst")
    _dma_start(soc, SRAM_BASE, 0x40000000, 64, irq_en=False)
    t_inject = tracker.fault_time
    soc.step(2)
    assert soc.read(D_STATUS) & ERROR
    assert soc.read(D_ERR) == 1
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    soc.write(D_IRQ_CLEAR, 1)
    assert soc.read(D_STATUS) == 0
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": True})
    return _finish(tracker, snap0, _snap(soc) | {"dma_bytes": 0}, row)


def case_dma_timeout(soc, inj, rep):
    nbytes = 64
    burst = soc.config["dma_burst"]
    lat = soc.config["dma_latency_per_word_ticks"]
    budget = 4 * _expected_dma_ticks(nbytes, burst, lat)  # modeled
    row = _base_row("dma-timeout", rep, budget)
    tracker = RecoveryTracker()
    _pattern(soc, SRAM_BASE, nbytes)
    soc.write(INTC_ENABLE, 1 << IRQ_DMA)
    snap0 = _snap(soc)
    _dma_start(soc, SRAM_BASE, SRAM_BASE + 0x1000, nbytes, irq_en=True)
    tracker.on_fault(soc.ticks, "dma-timeout")
    t_inject = tracker.fault_time
    inj.inject(Fault("dma-timeout"))
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
    soc.write(INTC_CLEAR, IRQ_DMA)
    assert soc.read(D_STATUS) == 0
    tracker.on_recovered(soc.ticks)
    # Post-recovery health proof: clean transfer completes byte-correct,
    # including the full IRQ path.
    _dma_start(soc, SRAM_BASE, SRAM_BASE + 0x1000, nbytes, irq_en=True)
    soc.run_until(lambda: soc.read(D_STATUS) & (DONE | ERROR), max_ticks=1000)
    ok = bool(soc.read(D_STATUS) & DONE) and _verify(soc, SRAM_BASE + 0x1000, nbytes)
    assert soc.read(INTC_PENDING) & (1 << IRQ_DMA)
    assert soc.read(INTC_ACK) == IRQ_DMA
    soc.write(D_IRQ_CLEAR, 1)
    soc.write(INTC_CLEAR, IRQ_DMA)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": ok})
    snap1 = _snap(soc)
    return _finish(tracker, snap0, snap1, row)


def case_uart_stuck(soc, inj, rep):
    lat = soc.config["uart_latency_ticks"]
    budget = 4 * lat  # modeled
    row = _base_row("uart-stuck", rep, budget)
    tracker = RecoveryTracker()
    soc.write(U_CTRL, 0x1)
    snap0 = _snap(soc)
    assert soc.write(U_TXDATA, 0x55) == 0
    tracker.on_fault(soc.ticks, "uart-stuck")
    t_inject = tracker.fault_time
    inj.inject(Fault("uart-stuck-busy"))
    el = 0
    while el < budget:
        if soc.read(U_STATUS) & RX_VALID:
            break
        soc.step(1)
        el += 1
    assert not (soc.read(U_STATUS) & RX_VALID)
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    inj.clear("uart-stuck-busy")
    soc.run_until(lambda: bool(soc.read(U_STATUS) & RX_VALID), max_ticks=4 * lat)
    tracker.on_recovered(soc.ticks)
    ok = soc.read(0x20000004) == 0x55  # RXDATA byte intact
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": ok})
    return _finish(tracker, snap0, _snap(soc) | {"dma_bytes": 0}, row)


def case_irq_storm_timer(soc, inj, rep):
    budget = 64  # modeled observation window
    row = _base_row("irq-storm-timer", rep, budget)
    tracker = RecoveryTracker()
    soc.write(INTC_ENABLE, 1 << IRQ_TIMER)
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, "irq-storm-timer")
    t_inject = tracker.fault_time
    soc.write(T_LOAD, 2)
    soc.write(T_CTRL, 0x1 | 0x2 | 0x4)
    soc.step(20)
    assert soc.read(INTC_PENDING) == (1 << IRQ_TIMER)
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    assert soc.read(INTC_ACK) == IRQ_TIMER
    assert soc.read(INTC_ACK) == 0xFFFFFFFF  # coalesced: no duplicates
    soc.write(T_CTRL, 0)  # stop source
    soc.write(T_IRQ_CLEAR, 0x1)
    soc.write(INTC_CLEAR, IRQ_TIMER)
    assert soc.read(INTC_PENDING) == 0
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": True,
                "storm_ack_order": [IRQ_TIMER]})
    return _finish(tracker, snap0, _snap(soc) | {"dma_bytes": 0}, row)


def case_irq_storm_mixed(soc, inj, rep):
    budget = 64
    row = _base_row("irq-storm-mixed", rep, budget)
    tracker = RecoveryTracker()
    soc.write(INTC_ENABLE, 0x7)
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, "irq-storm-mixed")
    t_inject = tracker.fault_time
    soc.write(T_LOAD, 5)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, 16)
    soc.write(D_CTRL, 0x1 | 0x2)
    soc.write(U_CTRL, 0x1)
    soc.write(U_TXDATA, 0x41)
    soc.run_until(lambda: soc.read(INTC_PENDING) == 0x7, max_ticks=50)
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    order = []
    for _ in range(3):
        order.append(soc.read(INTC_ACK))
        soc.write(INTC_CLEAR, order[-1])
    assert order == [IRQ_TIMER, IRQ_DMA, IRQ_UART]
    soc.write(D_IRQ_CLEAR, 1)
    soc.write(T_IRQ_CLEAR, 0x1)
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": True,
                "storm_ack_order": order})
    snap1 = _snap(soc)
    return _finish(tracker, snap0, snap1, row)


def _mmio_case(soc, inj, rep, name, op):
    budget = 1  # modeled: synchronous BusError
    row = _base_row(name, rep, budget)
    tracker = RecoveryTracker()
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, name)
    t_inject = tracker.fault_time
    raised = False
    try:
        op(soc)
    except BusError:
        raised = True
    assert raised, f"{name} did not raise BusError"
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    # Recovery proof: a legal access still works afterwards.
    soc.write(U_CTRL, 0x1)
    assert soc.read(U_CTRL) == 0x1
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": True})
    return _finish(tracker, snap0, _snap(soc) | {"dma_bytes": 0}, row)


def case_mmio_unmapped_read(soc, inj, rep):
    return _mmio_case(soc, inj, rep, "mmio-unmapped-read",
                      lambda s: s.read(0x30000000))


def case_mmio_unmapped_write(soc, inj, rep):
    return _mmio_case(soc, inj, rep, "mmio-unmapped-write",
                      lambda s: s.write(0x30000000, 1))


def case_mmio_ro_write(soc, inj, rep):
    return _mmio_case(soc, inj, rep, "mmio-ro-write",
                      lambda s: s.write(U_STATUS, 0xFF))


def case_mmio_wo_read(soc, inj, rep):
    return _mmio_case(soc, inj, rep, "mmio-wo-read",
                      lambda s: s.read(U_TXDATA))


def case_mmio_bad_offset(soc, inj, rep):
    return _mmio_case(soc, inj, rep, "mmio-bad-offset",
                      lambda s: s.read(UART_BASE + 0x1C))


def case_timer_reset(soc, inj, rep):
    budget = 8
    row = _base_row("timer-reset", rep, budget)
    tracker = RecoveryTracker()
    soc.write(INTC_ENABLE, 1 << IRQ_TIMER)
    soc.write(T_LOAD, 4)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.run_until(lambda: soc.read(T_IRQ_STATUS) & 0x1, max_ticks=50)
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, "timer-reset")
    t_inject = tracker.fault_time
    soc.reset_peripherals()
    assert soc.read(INTC_PENDING) == 0  # cleared by reset: detected
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    assert soc.read(T_CTRL) == 0 and soc.read(T_LOAD) == 0
    soc.write(INTC_ENABLE, 1 << IRQ_TIMER)
    soc.write(T_LOAD, 4)
    soc.write(T_CTRL, 0x1 | 0x4)
    soc.run_until(lambda: soc.read(T_IRQ_STATUS) & 0x1, max_ticks=50)
    assert soc.read(INTC_ACK) == IRQ_TIMER
    soc.write(INTC_CLEAR, IRQ_TIMER)
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": True})
    return _finish(tracker, snap0, _snap(soc) | {"dma_bytes": 0}, row)


def case_reset_during_dma(soc, inj, rep):
    nbytes = 1024
    budget = 8
    row = _base_row("reset-during-dma", rep, budget)
    tracker = RecoveryTracker()
    _pattern(soc, SRAM_BASE, nbytes, tag=0xD0000000)
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1)
    soc.step(nbytes // 8)
    assert soc.read(D_STATUS) & BUSY
    snap0 = _snap(soc)
    tracker.on_fault(soc.ticks, "reset-during-dma")
    t_inject = tracker.fault_time
    soc.reset_peripherals()
    assert soc.read(D_STATUS) == 0  # back to idle: detected
    tracker.on_detected(soc.ticks)
    tracker.on_recovery_start()
    soc.write(D_SRC, SRAM_BASE)
    soc.write(D_DST, SRAM_BASE + 0x1000)
    soc.write(D_LEN, nbytes)
    soc.write(D_CTRL, 0x1)
    soc.run_until(lambda: soc.read(D_STATUS) & DONE, max_ticks=5000)
    ok = _verify(soc, SRAM_BASE + 0x1000, nbytes, tag=0xD0000000)
    tracker.on_recovered(soc.ticks)
    row.update({"injection_point": t_inject,
                "detection_point": tracker.detection_time,
                "recovery_point": tracker.recovery_time,
                "destination_match": ok})
    snap1 = _snap(soc)
    return _finish(tracker, snap0, snap1, row)


CASES = {
    "dma-invalid-src": case_dma_invalid_src,
    "dma-invalid-dst": case_dma_invalid_dst,
    "dma-timeout": case_dma_timeout,
    "uart-stuck": case_uart_stuck,
    "irq-storm-timer": case_irq_storm_timer,
    "irq-storm-mixed": case_irq_storm_mixed,
    "mmio-unmapped-read": case_mmio_unmapped_read,
    "mmio-unmapped-write": case_mmio_unmapped_write,
    "mmio-ro-write": case_mmio_ro_write,
    "mmio-wo-read": case_mmio_wo_read,
    "mmio-bad-offset": case_mmio_bad_offset,
    "timer-reset": case_timer_reset,
    "reset-during-dma": case_reset_during_dma,
}

ALIASES = {
    "dma-invalid": ["dma-invalid-src", "dma-invalid-dst"],
    "irq-storm": ["irq-storm-timer", "irq-storm-mixed"],
    "mmio-invalid": ["mmio-unmapped-read", "mmio-unmapped-write",
                     "mmio-ro-write", "mmio-wo-read", "mmio-bad-offset"],
}


def _expand(names):
    out = []
    for n in names:
        if n in ALIASES:
            out.extend(ALIASES[n])
        elif n in CASES:
            out.append(n)
        else:
            raise SystemExit(f"unknown fault {n!r} (cases: {sorted(CASES)}; "
                             f"aliases: {sorted(ALIASES)})")
    return out


def _stats(vals):
    vals = sorted(vals)
    n = len(vals)
    return {"n": n, "min": vals[0], "max": vals[-1],
            "mean": sum(vals) / n if n else 0}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fault-injection benchmark (measured).")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--faults", default="dma-invalid,dma-timeout,uart-stuck,irq-storm,mmio-invalid")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "results" / "fault_injection.json"))
    args = ap.parse_args()
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")

    config = load_config(args.config)
    faults = _expand([f for f in args.faults.split(",") if f.strip()])
    runs = []
    for rep in range(args.reps):
        for name in faults:
            soc = SoC(config)
            soc.boot()
            inj = FaultInjector(soc)
            row = CASES[name](soc, inj, rep)
            runs.append(row)

    det = True
    seen: dict[tuple, set] = {}
    for r in runs:
        key = (r["fault"],)
        seen.setdefault(key, set()).add((
            r["detection_latency_ticks"], r["recovery_latency_ticks"],
            r["final_state"]))
    # Reps of one fault must agree on latencies/state (deterministic model).
    by_fault: dict[str, list] = {}
    for r in runs:
        by_fault.setdefault(r["fault"], []).append(r)
    deterministic = all(
        len({(x["detection_latency_ticks"], x["recovery_latency_ticks"],
              x["final_state"]) for x in v}) == 1
        for v in by_fault.values()
    )
    det = det and deterministic

    summary = {}
    for name in faults:
        v = by_fault[name]
        summary[name] = {
            "runs": len(v),
            "deterministic": len({(x["detection_latency_ticks"],
                                   x["recovery_latency_ticks"],
                                   x["final_state"]) for x in v}) == 1,
            "detection_latency": _stats([x["detection_latency_ticks"] for x in v]),
            "recovery_latency": _stats([x["recovery_latency_ticks"] for x in v]),
            "final_states": {s: sum(1 for x in v if x["final_state"] == s)
                             for s in {x["final_state"] for x in v}},
            "irq_total": sum(x["irq_count"] for x in v),
            "destination_match_all": all(x["destination_match"] for x in v),
        }

    payload = {
        "params": {
            "config": pathlib.Path(args.config).name,
            "config_values": {
                "cpu_frequency_mhz": config.get("cpu_frequency_mhz"),
                "dma_burst": config.get("dma_burst"),
                "dma_latency_per_word_ticks": config.get("dma_latency_per_word_ticks"),
                "ram_latency_ticks": config.get("ram_latency_ticks"),
                "uart_latency_ticks": config.get("uart_latency_ticks"),
            },
            "faults": faults,
            "repetitions": args.reps,
            "deterministic_across_reps": det,
            "note": "ticks/counters measured in the virtual SoC timing model; "
                    "latencies derived by subtraction; budgets modeled.",
        },
        "runs": runs,
        "summary": summary,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"config: {payload['params']['config']} faults={faults} "
          f"reps={args.reps} deterministic={det}")
    print(f"{'fault':>20} {'det':>5} {'rec':>5} {'final':>10} {'irq':>4} {'match'}")
    for name in faults:
        s = summary[name]
        print(f"{name:>20} {s['detection_latency']['mean']:>5.1f} "
              f"{s['recovery_latency']['mean']:>5.1f} "
              f"{str(s['final_states']):>10} {s['irq_total']:>4} "
              f"{s['destination_match_all']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
