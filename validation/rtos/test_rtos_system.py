"""RTOS system validation: preemption, deadlines, starvation, determinism."""
from __future__ import annotations

from rtos.kernel import RtosQueue, Scheduler
from rtos.tasks import (acquisition_task, diagnostic_task, processing_task,
                        telemetry_task)


def _pipeline(soc, *, period=20, acq=1, proc=6, telem=2, qdepth=8,
              deadline=60, proc_prio=4, telem_prio=2, max_items=10,
              run_ticks=3000):
    sch = Scheduler(soc)
    q1, q2 = RtosQueue("in", qdepth), RtosQueue("out", qdepth)
    sa, sp, st, sd = {}, {}, {}, {}
    sch.create_task("acq", 3, acquisition_task(period, acq, q1, deadline,
                                               sa, max_items=max_items))
    sch.create_task("proc", proc_prio, processing_task(q1, q2, proc, sp))
    sch.create_task("tele", telem_prio, telemetry_task(q2, telem, st))
    sch.create_task("diag", 1, diagnostic_task(50, sch, sd))
    sch.run(run_ticks)
    return sch, q1, q2, sa, sp, st, sd


def test_priority_preempts_compute(soc):
    sch = Scheduler(soc)
    ran = []

    def low():
        yield {"op": "compute", "ticks": 10}
        ran.append("low-done")

    def high():
        yield {"op": "delay", "ticks": 3}
        ran.append("high-done")

    sch.create_task("low", 1, low())
    sch.create_task("high", 5, high())
    sch.run(30)
    # High becomes ready at tick 4 and preempts low's 10-tick compute.
    assert ran == ["high-done", "low-done"]
    assert sch.context_switches >= 2


def test_no_deadlock_bounded_pipeline(soc):
    sch, q1, q2, sa, sp, st, sd = _pipeline(soc)
    assert sa.get("produced") == 10
    assert len(st.get("latency", [])) == 10  # everything drained
    assert q1.stats()["depth"] == 0 and q2.stats()["depth"] == 0


def test_no_item_corruption(soc):
    sch = Scheduler(soc)
    q = RtosQueue("q", 4)
    seen = []

    def producer():
        for i in range(50):
            assert (yield {"op": "qsend", "queue": q, "item": (i, i * i),
                           "timeout": None})

    def consumer():
        for _ in range(50):
            seen.append((yield {"op": "qrecv", "queue": q, "timeout": None}))

    sch.create_task("prod", 2, producer())
    sch.create_task("cons", 3, consumer())
    sch.run(2000)
    assert seen == [(i, i * i) for i in range(50)]


def test_deadline_detection(soc):
    # Overload: processing slower than arrival -> misses must be flagged.
    sch, q1, q2, sa, sp, st, sd = _pipeline(
        soc, period=10, proc=30, deadline=40, max_items=12, run_ticks=4000)
    assert st.get("misses", 0) > 0
    assert all(v > 0 for v in st["latency"])


def test_starvation_detection(soc):
    # Saturated high-priority processing starves low-priority telemetry.
    sch, q1, q2, sa, sp, st, sd = _pipeline(
        soc, period=5, acq=0, proc=20, telem=2, qdepth=4,
        proc_prio=5, telem_prio=1, max_items=30, run_ticks=4000)
    tele_runs = sch.by_name["tele"].run_ticks
    proc_runs = sch.by_name["proc"].run_ticks
    assert len(proc_runs) > 0
    if len(tele_runs) >= 2:
        max_gap = max(b - a for a, b in zip(tele_runs, tele_runs[1:]))
    else:
        max_gap = 10 ** 9  # never ran twice: fully starved
    assert max_gap > 5 * 5  # gap exceeds 5x the acquisition period


def test_deterministic_repeat(config):
    from soc.soc import SoC

    def once():
        s = SoC(config)
        s.boot()
        sch, q1, q2, sa, sp, st, sd = _pipeline(
            s, period=20, proc=6, max_items=10, run_ticks=3000)
        return (tuple(st.get("latency", [])), st.get("misses", 0),
                sch.context_switches, q1.stats()["max_depth"])

    assert once() == once()


def test_priority_swap_changes_behavior(soc):
    # Overloaded pipeline (13 ticks work per 10-tick period) so scheduling
    # order actually matters.
    base = dict(period=10, acq=1, proc=9, telem=5, qdepth=4, deadline=200,
                max_items=30, run_ticks=6000)
    sch_hi, _, _, _, _, st_hi, _ = _pipeline(soc, proc_prio=5, telem_prio=2,
                                             **base)
    from soc.soc import SoC
    s2 = SoC(soc.config)
    s2.boot()
    sch_lo, _, _, _, _, st_lo, _ = _pipeline(s2, proc_prio=2, telem_prio=5,
                                             **base)
    # Same workload both ways; scheduling must differ observably.
    runs_hi = {t.name: len(t.run_ticks) for t in sch_hi.tasks}
    runs_lo = {t.name: len(t.run_ticks) for t in sch_lo.tasks}
    assert runs_hi != runs_lo
    assert (st_hi.get("latency") != st_lo.get("latency")
            or st_hi.get("misses", 0) != st_lo.get("misses", 0))
