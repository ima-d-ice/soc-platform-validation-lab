"""Deterministic RTOS scheduler with FreeRTOS-like semantics (Phase 6).

MODEL, not the FreeRTOS kernel: priority-preemptive scheduling, queues,
task notifications, mutexes, and delay/delay_until all execute in virtual
SoC model ticks driven by the bound SoC instance (each scheduler tick also
steps the SoC once, so timers/UART/DMA share the same clock). No wall-clock
use, no randomness, fully repeatable. See docs/rtos.md for the exact
semantics mapping (what is real FreeRTOS behavior vs host/model behavior).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

READY = "READY"
RUNNING = "RUNNING"
BLOCKED = "BLOCKED"

MAX_STEPS_PER_TICK = 32


@dataclass
class WorkItem:
    seq: int
    birth: int
    deadline: int
    payload: int = 0


class RtosQueue:
    """Bounded FIFO. Blocking send/receive with tick timeouts."""

    def __init__(self, name: str, capacity: int):
        assert capacity >= 1
        self.name = name
        self.capacity = capacity
        self._dq: deque = deque()
        self.sends = 0
        self.receives = 0
        self.drops = 0  # timeout==0 sends refused while full
        self.send_timeouts = 0
        self.recv_timeouts = 0
        self.max_depth = 0

    def __len__(self):
        return len(self._dq)

    def try_send(self, item) -> bool:
        if len(self._dq) >= self.capacity:
            return False
        self._dq.append(item)
        self.sends += 1
        if len(self._dq) > self.max_depth:
            self.max_depth = len(self._dq)
        return True

    def try_recv(self):
        if not self._dq:
            return None
        self.receives += 1
        return self._dq.popleft()

    def stats(self) -> dict:
        return {"name": self.name, "capacity": self.capacity,
                "depth": len(self._dq), "sends": self.sends,
                "receives": self.receives, "drops": self.drops,
                "send_timeouts": self.send_timeouts,
                "recv_timeouts": self.recv_timeouts,
                "max_depth": self.max_depth}


class RtosMutex:
    """Plain non-recursive mutex. No priority inheritance (documented)."""

    def __init__(self, name: str):
        self.name = name
        self.owner = None
        self.takes = 0
        self.contentions = 0


class Task:
    def __init__(self, name: str, priority: int, gen, scheduler=None):
        self.name = name
        self.priority = priority
        self.gen = gen
        self.scheduler = scheduler
        self.state = READY
        self.result = None  # value sent into generator on next advance
        self.compute_remaining = 0
        self.wake_at: int | None = None  # delay / delay_until / timeout deadline
        self.wait_kind: str | None = None  # delay|qsend|qrecv|notify|mutex
        self.wait_obj = None
        self.wait_item = None
        self.next_wake: int | None = None  # delay_until anchor
        self.notify_value = None
        self.notify_count = 0
        self.run_ticks: list[int] = []  # model ticks this task ran
        self.wake_log: list[dict] = []  # delay_until expected vs actual
        self.finished = False


class Scheduler:
    """Priority-preemptive tick scheduler bound to a SoC clock."""

    def __init__(self, soc):
        self.soc = soc
        self.now = 0
        self.tasks: list[Task] = []
        self.by_name: dict[str, Task] = {}
        self.context_switches = 0
        self.idle_ticks = 0
        self._last_run: str | None = None
        self._rr: list[str] = []  # round-robin order for priority ties

    # -- task management (xTaskCreate-like) --
    def create_task(self, name: str, priority: int, gen) -> Task:
        assert name not in self.by_name, f"duplicate task {name}"
        t = Task(name, priority, gen, scheduler=self)
        self.tasks.append(t)
        self.by_name[name] = t
        self._rr.append(name)
        return t

    def notify(self, name: str, value=1) -> None:
        t = self.by_name[name]
        t.notify_value = value
        t.notify_count += 1

    # -- main loop --
    def tick(self) -> str | None:
        self.now += 1
        self.soc.step(1)
        self._progress_blocked()
        cand = [t for t in self.tasks
                if t.state == READY and not t.finished]
        if not cand:
            self.idle_ticks += 1
            self._last_run = None
            return None
        top = max(t.priority for t in cand)
        tied = [t for t in cand if t.priority == top]
        # Round-robin among ties: earliest in rotating order.
        order = [n for n in self._rr if n in {t.name for t in tied}]
        chosen = self.by_name[order[0]]
        self._rr.remove(chosen.name)
        self._rr.append(chosen.name)
        if self._last_run is not None and self._last_run != chosen.name:
            self.context_switches += 1
        self._last_run = chosen.name
        chosen.run_ticks.append(self.now)
        self._run_task(chosen)
        return chosen.name

    def run(self, ticks: int) -> None:
        for _ in range(ticks):
            self.tick()

    # -- internals --
    def _progress_blocked(self) -> None:
        for t in self.tasks:
            if t.state != BLOCKED or t.finished:
                continue
            kind = t.wait_kind
            if kind == "delay" or kind == "delay_until":
                if t.wake_at is not None and self.now >= t.wake_at:
                    t.state = READY
                    t.wait_kind = None
                    if kind == "delay_until":
                        exp = t.wait_exp
                        missed = self.now > exp
                        t.wake_log.append(
                            {"expected": exp, "actual": self.now,
                             "missed": missed})
                        t.result = {"actual": self.now, "expected": exp,
                                    "missed": missed}
                    else:
                        t.result = True
                    t.wake_at = None
            elif kind == "qsend":
                q = t.wait_obj
                if q.try_send(t.wait_item):
                    t.state = READY
                    t.result = True
                    t.wait_kind = None
                    t.wait_item = None
                elif t.wake_at is not None and self.now >= t.wake_at:
                    t.state = READY
                    t.result = False
                    t.wait_kind = None
                    t.wait_item = None
                    if t.wait_timeout_zero:
                        q.drops += 1
                    else:
                        q.send_timeouts += 1
            elif kind == "qrecv":
                q = t.wait_obj
                item = q.try_recv()
                if item is not None:
                    t.state = READY
                    t.result = item
                    t.wait_kind = None
                elif t.wake_at is not None and self.now >= t.wake_at:
                    t.state = READY
                    t.result = None
                    t.wait_kind = None
                    q.recv_timeouts += 1
            elif kind == "notify_wait":
                if t.notify_value is not None:
                    t.state = READY
                    t.result = t.notify_value
                    t.notify_value = None
                    t.wait_kind = None
                elif t.wake_at is not None and self.now >= t.wake_at:
                    t.state = READY
                    t.result = None
                    t.wait_kind = None
            elif kind == "mutex_take":
                m = t.wait_obj
                if m.owner is None:
                    m.owner = t.name
                    m.takes += 1
                    t.state = READY
                    t.result = True
                    t.wait_kind = None
                elif t.wake_at is not None and self.now >= t.wake_at:
                    t.state = READY
                    t.result = False
                    t.wait_kind = None

    def _run_task(self, t: Task) -> None:
        steps = 0
        while steps < MAX_STEPS_PER_TICK:
            steps += 1
            if t.compute_remaining > 0:
                # Occupies the CPU this tick; one unit consumed.
                t.compute_remaining -= 1
                if t.compute_remaining > 0:
                    t.state = READY
                    return
                self._advance(t, True)
                if t.state != READY or t.finished:
                    return
                continue
            # Freshly scheduled: advance generator with stored result.
            # Consume it first so an immediately-completing op can store
            # the next result without it being wiped.
            res, t.result = t.result, None
            self._advance(t, res)
            if t.state != READY or t.finished:
                return
            # Immediate-result ops loop within the tick (bounded).

    def _advance(self, t: Task, value) -> None:
        try:
            op = t.gen.send(value) if t._started else next(t.gen)
        except StopIteration:
            t.finished = True
            t.state = READY
            return
        t._started = True
        self._exec_op(t, op)

    def _exec_op(self, t: Task, op: dict) -> None:
        kind = op["op"]
        if kind == "compute":
            # Occupies the CPU for exactly n ticks; the run loop below
            # consumes one unit per tick the task is scheduled.
            n = max(0, int(op.get("ticks", 0)))
            if n == 0:
                return
            t.compute_remaining = n
            t.state = READY
            return
        if kind == "delay":
            t.state = BLOCKED
            t.wait_kind = "delay"
            t.wake_at = self.now + max(0, int(op.get("ticks", 0)))
            return
        if kind == "delay_until":
            p = max(1, int(op.get("period", 1)))
            if t.next_wake is None:
                t.next_wake = self.now + p
            else:
                t.next_wake += p
                if t.next_wake <= self.now:
                    t.next_wake = self.now + 1  # overrun catch-up
            t.state = BLOCKED
            t.wait_kind = "delay_until"
            t.wake_at = t.next_wake
            t.wait_exp = t.next_wake
            return
        if kind == "qsend":
            q = op["queue"]
            timeout = op.get("timeout")
            if q.try_send(op["item"]):
                t.result = True
                return
            if timeout == 0:
                q.drops += 1
                t.result = False
                return
            t.state = BLOCKED
            t.wait_kind = "qsend"
            t.wait_obj = q
            t.wait_item = op["item"]
            t.wait_timeout_zero = False
            t.wake_at = None if timeout is None else self.now + timeout
            return
        if kind == "qrecv":
            q = op["queue"]
            timeout = op.get("timeout")
            item = q.try_recv()
            if item is not None:
                t.result = item  # generator resumes with the item
                return
            if timeout == 0:
                q.recv_timeouts += 1
                t.result = None
                return
            t.state = BLOCKED
            t.wait_kind = "qrecv"
            t.wait_obj = q
            t.wake_at = None if timeout is None else self.now + timeout
            return
        if kind == "notify_wait":
            timeout = op.get("timeout")
            if t.notify_value is not None:
                t.result = t.notify_value
                t.notify_value = None
                return
            if timeout == 0:
                t.result = None
                return
            t.state = BLOCKED
            t.wait_kind = "notify_wait"
            t.wake_at = None if timeout is None else self.now + timeout
            return
        if kind == "notify":
            self.notify(op["task"], op.get("value", 1))
            return
        if kind == "now":
            t.result = self.now  # immediate read of the model clock
            return
        if kind == "mutex_take":
            m = op["mutex"]
            timeout = op.get("timeout")
            if m.owner is None or m.owner == t.name:
                m.owner = t.name
                m.takes += 1
                t.result = True
                return
            m.contentions += 1
            if timeout == 0:
                t.result = False
                return
            t.state = BLOCKED
            t.wait_kind = "mutex_take"
            t.wait_obj = m
            t.wake_at = None if timeout is None else self.now + timeout
            return
        if kind == "mutex_give":
            m = op["mutex"]
            assert m.owner == t.name, f"{t.name} gives unowned mutex"
            # Hand off to highest-priority waiter if any.
            waiters = [w for w in self.tasks
                       if w.state == BLOCKED and w.wait_kind == "mutex_take"
                       and w.wait_obj is m]
            if waiters:
                top = max(w.priority for w in waiters)
                nxt = [w for w in waiters if w.priority == top][0]
                m.owner = nxt.name
                m.takes += 1
                nxt.state = READY
                nxt.result = True
                nxt.wait_kind = None
                nxt.wake_at = None
            else:
                m.owner = None
            return
        raise AssertionError(f"unknown op {kind!r}")


# Generator-protocol flag: first advance uses next(), later ones send().
# Set as a class default; instances shadow it once started.
Task._started = False  # noqa: SLF001 (intentional protocol flag)
