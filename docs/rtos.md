# RTOS Scheduling Study (Phase 6)

> **Virtual-model disclaimer.** Tick counts, latencies, jitter, and miss
> rates below are measured in virtual SoC model ticks. They are not MCU
> timing, not FreeRTOS-on-hardware timing, and not silicon data.

## What is real FreeRTOS behavior vs host/model behavior

The scheduler in `rtos/kernel.py` is a **model of FreeRTOS scheduling
semantics**, not the FreeRTOS kernel source:

| Real FreeRTOS semantics (modeled faithfully) | Host/model behavior (not hardware) |
|---|---|
| Priority-preemptive selection, tie round-robin | Time base = shared SoC model tick, not SysTick hardware |
| Blocking queues with timeouts, FIFO order | Work costs are tick parameters, not instruction timing |
| Task notifications (overwrite + count) | No ISRs drive notifications here; tasks only |
| Non-recursive mutex + priority-ordered handoff | **No priority inheritance** (documented gap) |
| `vTaskDelay` / `vTaskDelayUntil` periodic semantics incl. overrun catch-up | Periods exact in ticks; hardware clock drift does not exist |
| Context switch on preemption/reschedule | Switch cost is zero ticks (counted, not charged) |

There is deliberately no POSIX/FreeRTOS port: a wall-clock port would break
the determinism rule (identical scenario → identical results, verified by
`deterministic_across_reps: true`).

## Architecture (unchanged SoC map)

```text
SoC model (shared tick clock)
  ↓ step(1) per scheduler tick
HAL/drivers (existing C + Python models; tasks use modeled I/O costs)
  ↓
Scheduler (priorities, queues, notifications, mutex)
  ↓
Acquisition → Processing → Telemetry (+ Diagnostic monitor)
```

`firmware/rtos/` stays a pointer note; the schedulable RTS runs in Python
against the same SoC clock so timers/peripherals advance underneath tasks.

## Metric classes

* **Measured:** per-item latencies, actual wake periods, deadline misses,
  queue depths/drops/timeouts, context switches, idle ticks, run-gap
  starvation events, completions.
* **Derived:** mean/p50/p99/max, jitter (period std), miss rate.
* **Modeled:** work ticks/item, periods, deadlines, queue capacities, the
  starvation rule (run-gap > 5× acquisition period).

## REAL OBSERVATIONS (`configs/base.yaml`, 5 reps, deterministic)

Priority (identical overloaded workload, 15 ticks work / 10-tick period):

| scenario | mean lat | p99 | starved |
|---|---|---|---|
| proc HIGH / telem LOW | 107.2 | 135 | diag, tele |
| proc LOW / telem HIGH | 57.1 | 72 | diag only |

Processing load (deadline 9 ticks): latency == proc+2 ticks exactly
(3,4,6,10,14,18); 100% miss rate from proc-8 upward — the knee is between
proc-4 and proc-8. No queueing (period 20 > service), so the knee is pure
per-item cost vs deadline.

Queue pressure (5-tick period, 8-tick service): depth 1→16 drops fall
19→0 while mean latency rises 26.3→132.6 and miss rate 0%→87.5% — the
classic drop-vs-wait tradeoff, measured both sides. Telemetry starves at
every depth (service > period saturates the CPU).

Periodic: P-20/P-40 exact (jitter 0.00, no misses); P-10 overloaded shows
wake jitter 1.43 ticks with catch-up overruns and 100% misses.

## MODEL BEHAVIOR notes

* Context-switch cost is counted, never charged; zero-cost switches flatter
  small-work differences vs hardware.
* `delay_until` catch-up (`next_wake = now + 1` on overrun) is what creates
  the P-10 jitter signature; hardware SysTick overrun handling differs.
* Starvation is a post-analysis gap rule, not an RTOS primitive.
