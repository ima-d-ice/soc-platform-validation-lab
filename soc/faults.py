"""Deterministic fault injection + recovery tracking (Phase 5).

Additive to the model: latching faults default to off, so every Phase-1–4
test behaves identically with this module imported. No register map
changes, no new IRQ mechanism, no randomness, no wall-clock use.

Fault kinds:
- Latching (need a model hook): ``dma-timeout`` (freeze DMA countdown),
  ``uart-stuck-busy`` (freeze UART busy countdown).
- Stimulus (driven through existing MMIO/bus by tests/harness, tracked
  here for uniformity): ``dma-invalid-src/dst``, ``irq-storm-timer/mixed``,
  ``mmio-*``, ``timer-reset-pending``, ``reset-during-dma``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Recovery states (validation level, not a safety framework).
NORMAL = "NORMAL"
FAULT_DETECTED = "FAULT_DETECTED"
RECOVERY = "RECOVERY"
RECOVERED = "RECOVERED"
UNRECOVERABLE = "UNRECOVERABLE"

# Faults that latch inside the peripheral models.
LATCH_FAULTS = ("dma-timeout", "uart-stuck-busy")


@dataclass
class Fault:
    """A named fault with optional params and schedule info."""

    name: str
    params: dict = field(default_factory=dict)
    at_tick: int | None = None
    event: Callable | None = None  # predicate(soc) -> bool


class RecoveryTracker:
    """Tiny explicit recovery state machine with measured timestamps."""

    LEGAL = {
        NORMAL: (FAULT_DETECTED,),
        FAULT_DETECTED: (RECOVERY, UNRECOVERABLE),
        RECOVERY: (RECOVERED, UNRECOVERABLE),
        RECOVERED: (),
        UNRECOVERABLE: (),
    }

    def __init__(self):
        self.current_state = NORMAL
        self.fault_type: str | None = None
        self.fault_time: int | None = None
        self.detection_time: int | None = None
        self.recovery_time: int | None = None
        self.final_state: str | None = None

    def _go(self, nxt: str) -> None:
        if nxt not in self.LEGAL[self.current_state]:
            raise AssertionError(f"illegal recovery transition {self.current_state} -> {nxt}")
        self.current_state = nxt

    def on_fault(self, tick: int, fault_type: str) -> None:
        if self.current_state != NORMAL:
            raise AssertionError("on_fault requires NORMAL state")
        self.fault_type = fault_type
        self.fault_time = tick

    def on_detected(self, tick: int) -> None:
        self._go(FAULT_DETECTED)
        self.detection_time = tick

    def on_recovery_start(self) -> None:
        self._go(RECOVERY)

    def on_recovered(self, tick: int) -> None:
        self._go(RECOVERED)
        self.recovery_time = tick
        self.final_state = RECOVERED

    def on_unrecoverable(self, tick: int) -> None:
        nxt = UNRECOVERABLE
        if self.current_state not in self.LEGAL or nxt not in self.LEGAL[self.current_state]:
            raise AssertionError(f"illegal recovery transition {self.current_state} -> {nxt}")
        self.current_state = UNRECOVERABLE
        self.recovery_time = tick
        self.final_state = UNRECOVERABLE

    @property
    def detection_latency(self) -> int | None:  # derived
        if self.fault_time is None or self.detection_time is None:
            return None
        return self.detection_time - self.fault_time

    @property
    def recovery_latency(self) -> int | None:  # derived
        if self.detection_time is None or self.recovery_time is None:
            return None
        return self.recovery_time - self.detection_time

    def record(self) -> dict:
        return {
            "current_state": self.current_state,
            "fault_type": self.fault_type,
            "fault_time": self.fault_time,
            "detection_time": self.detection_time,
            "recovery_time": self.recovery_time,
            "final_state": self.final_state,
            "detection_latency_ticks": self.detection_latency,
            "recovery_latency_ticks": self.recovery_latency,
        }


class FaultInjector:
    """Schedules and applies deterministic faults to a bound SoC."""

    def __init__(self, soc):
        self._soc = soc
        self._active: dict[str, Fault] = {}
        self._scheduled: list[Fault] = []

    # -- immediate API --
    def inject(self, fault: Fault) -> Fault:
        self._apply_latch(fault, True)
        self._active[fault.name] = fault
        return fault

    def clear(self, name: str) -> None:
        fault = self._active.pop(name, None)
        if fault is not None:
            self._apply_latch(fault, False)
        # Clearing a never-latched name is a no-op (still deterministic).

    def is_active(self, name: str) -> bool:
        return name in self._active

    # -- scheduled API --
    def apply_at_tick(self, fault: Fault, tick: int) -> Fault:
        fault.at_tick = tick
        self._scheduled.append(fault)
        return fault

    def apply_at_event(self, fault: Fault, predicate: Callable) -> Fault:
        fault.event = predicate
        self._scheduled.append(fault)
        return fault

    def poll(self) -> list[Fault]:
        """Fire due scheduled faults. Call after every soc.step()."""
        fired: list[Fault] = []
        still: list[Fault] = []
        for fault in self._scheduled:
            due = False
            if fault.at_tick is not None and self._soc.ticks >= fault.at_tick:
                due = True
            elif fault.event is not None:
                try:
                    due = bool(fault.event(self._soc))
                except Exception:
                    due = False
            if due:
                self.inject(fault)
                fired.append(fault)
            else:
                still.append(fault)
        self._scheduled = still
        return fired

    # -- internals --
    def _apply_latch(self, fault: Fault, on: bool) -> None:
        if fault.name == "dma-timeout":
            self._soc.dma.fault_stuck_busy = on
        elif fault.name == "uart-stuck-busy":
            self._soc.uart.fault_stuck_busy = on
        elif fault.name in LATCH_FAULTS:
            raise AssertionError(f"unhandled latch fault {fault.name!r}")
        # Stimulus faults need no latch; tests/harness drive them via MMIO.
