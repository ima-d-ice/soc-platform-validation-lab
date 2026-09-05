"""Application tasks for the virtual-SoC RTOS study (Phase 6).

AcquisitionTask: periodic producer (modeled acquisition cost per sample).
ProcessingTask: consumes input queue, modeled compute per item, forwards.
TelemetryTask: drains output queue, modeled transmit cost, records
  end-to-end latency and deadline misses.
DiagnosticTask: lowest-priority periodic monitor sampling scheduler stats
  (its own wake jitter makes starvation visible).

All work costs are MODEL parameters in ticks, never hardware timings.
"""
from __future__ import annotations

from .kernel import WorkItem


def acquisition_task(period, acq_cost, out_queue, deadline_ticks,
                     stats, max_items=None):
    """Periodic producer. Drops (counts) when out_queue is full."""
    seq = 0
    produced = 0
    while max_items is None or produced < max_items:
        wake = yield {"op": "delay_until", "period": period}
        stats.setdefault("wake", []).append(wake)
        if acq_cost:
            yield {"op": "compute", "ticks": acq_cost}
        # Birth tick = acquisition completion (model clock read).
        now = yield {"op": "now"}
        item = WorkItem(seq=seq, birth=now,
                        deadline=now + deadline_ticks, payload=seq)
        ok = yield {"op": "qsend", "queue": out_queue, "item": item,
                    "timeout": 0}
        seq += 1
        if ok:
            produced += 1
    stats["produced"] = produced
    stats["attempted"] = seq
    return


def processing_task(in_queue, out_queue, cost_per_item, stats,
                    send_timeout=50):
    """Consume -> compute -> forward. Counts forward drops on timeout."""
    done = 0
    while True:
        item = yield {"op": "qrecv", "queue": in_queue, "timeout": None}
        yield {"op": "compute", "ticks": cost_per_item}
        ok = yield {"op": "qsend", "queue": out_queue, "item": item,
                    "timeout": send_timeout}
        done += 1
        if not ok:
            stats["forward_drops"] = stats.get("forward_drops", 0) + 1
    # (Infinite service loop by design; benchmark stops the scheduler.)


def telemetry_task(in_queue, tx_cost, stats):
    """Drain -> transmit. Records latency and deadline misses."""
    done = 0
    while True:
        item = yield {"op": "qrecv", "queue": in_queue, "timeout": None}
        if tx_cost:
            yield {"op": "compute", "ticks": tx_cost}
        now = yield {"op": "now"}
        latency = now - item.birth
        stats.setdefault("latency", []).append(latency)
        if now > item.deadline:
            stats["misses"] = stats.get("misses", 0) + 1
        done += 1
    # (Infinite service loop by design.)


def diagnostic_task(period, scheduler, stats):
    """Lowest-priority monitor: samples run-gap stats each period."""
    while True:
        wake = yield {"op": "delay_until", "period": period}
        stats.setdefault("wake", []).append(wake)
        gaps = {}
        for t in scheduler.tasks:
            runs = t.run_ticks
            if len(runs) >= 2:
                gaps[t.name] = max(b - a for a, b in zip(runs, runs[1:]))
            else:
                gaps[t.name] = 0
        stats.setdefault("gap_samples", []).append(
            {"at": wake["actual"], "gaps": gaps})
