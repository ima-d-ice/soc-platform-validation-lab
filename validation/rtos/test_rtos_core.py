"""RTOS core validation: creation, queues, notifications, mutex, timeouts."""
from __future__ import annotations

import pytest

from rtos.kernel import RtosMutex, RtosQueue, Scheduler


def _sched(soc):
    return Scheduler(soc)


def test_task_creation_and_priorities(soc):
    sch = _sched(soc)

    def sleeper():
        yield {"op": "delay", "ticks": 1000}

    sch.create_task("low", 1, sleeper())
    sch.create_task("high", 5, sleeper())
    assert sch.by_name["high"].priority == 5
    assert [t.name for t in sch.tasks] == ["low", "high"]
    with pytest.raises(AssertionError):
        sch.create_task("low", 2, sleeper())


def test_queue_communication_and_fifo(soc):
    sch = _sched(soc)
    q = RtosQueue("q", 4)
    got = []

    def producer():
        for i in range(3):
            assert (yield {"op": "qsend", "queue": q, "item": i,
                           "timeout": None})

    def consumer():
        for _ in range(3):
            got.append((yield {"op": "qrecv", "queue": q, "timeout": None}))

    sch.create_task("prod", 2, producer())
    sch.create_task("cons", 2, consumer())
    sch.run(50)
    assert got == [0, 1, 2]  # FIFO, no corruption
    assert q.sends == 3 and q.receives == 3 and q.drops == 0


def test_queue_full_drop_and_depth(soc):
    sch = _sched(soc)
    q = RtosQueue("q", 2)
    results = []

    def producer():
        for i in range(4):
            results.append((yield {"op": "qsend", "queue": q, "item": i,
                                   "timeout": 0}))

    sch.create_task("prod", 1, producer())
    sch.run(10)
    assert results == [True, True, False, False]
    assert q.drops == 2
    assert q.max_depth == 2


def test_queue_recv_timeout(soc):
    sch = _sched(soc)
    q = RtosQueue("q", 2)
    got = []

    def consumer():
        got.append((yield {"op": "qrecv", "queue": q, "timeout": 5}))

    sch.create_task("cons", 1, consumer())
    sch.run(20)
    assert got == [None]
    assert q.recv_timeouts == 1


def test_notification_wakes_waiter(soc):
    sch = _sched(soc)
    got = []

    def waiter():
        got.append((yield {"op": "notify_wait", "timeout": None}))

    def notifier():
        yield {"op": "delay", "ticks": 3}
        yield {"op": "notify", "task": "waiter", "value": 42}

    sch.create_task("waiter", 3, waiter())
    sch.create_task("notifier", 2, notifier())
    sch.run(20)
    assert got == [42]


def test_notification_timeout(soc):
    sch = _sched(soc)
    got = []

    def waiter():
        got.append((yield {"op": "notify_wait", "timeout": 4}))

    sch.create_task("waiter", 1, waiter())
    sch.run(20)
    assert got == [None]


def test_mutex_exclusion_and_handoff(soc):
    sch = _sched(soc)
    m = RtosMutex("m")
    order = []

    def worker(tag, hold):
        assert (yield {"op": "mutex_take", "mutex": m, "timeout": None})
        order.append(f"{tag}-in")
        yield {"op": "compute", "ticks": hold}
        order.append(f"{tag}-out")
        yield {"op": "mutex_give", "mutex": m}

    sch.create_task("a", 2, worker("a", 3))
    sch.create_task("b", 2, worker("b", 3))
    sch.run(60)
    # Critical sections never interleave.
    assert order == ["a-in", "a-out", "b-in", "b-out"]
    assert m.owner is None


def test_delay_and_periodic_wake(soc):
    sch = _sched(soc)
    wakes = []

    def periodic():
        for _ in range(3):
            wakes.append((yield {"op": "delay_until", "period": 10}))

    sch.create_task("p", 1, periodic())
    sch.run(60)
    assert [w["actual"] - w["expected"] for w in wakes] == [0, 0, 0]
    assert wakes[1]["expected"] - wakes[0]["expected"] == 10
