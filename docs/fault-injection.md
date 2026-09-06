# Fault Injection + Pre-Silicon System Validation (Phase 5)

> **Virtual-model disclaimer.** Everything below describes the host-native
> behavioral virtual SoC in this repository. Nothing here is ARM hardware,
> MCU DMA timing, silicon performance, bus bandwidth, or real interrupt
> latency. All tick/latency numbers are model ticks.

Core question: *how does system software behave when SoC peripherals or
system resources fail, and how quickly/correctly does the platform detect
and recover?*

Metric classes used throughout:

| Class | Meaning | Examples |
|---|---|---|
| **measured** | Directly observed from model ticks, PERF counters, registers | injection/detection/recovery tick, IRQ_COUNT, MEM_ACC, STALLS, STATUS bits |
| **derived** | Arithmetic on measured values | detection/recovery latency, throughput, crossover |
| **modeled** | Behavior defined by the virtual model | stuck-busy freeze, timeout budgets, CPU wait ticks |

## 1. Why fault injection exists

Pre-silicon validation must cover not only the happy path but the failure
modes software will meet on real hardware: bad descriptors, hung engines,
stuck peripherals, interrupt floods, illegal accesses, and resets landing
mid-activity. This phase makes those failures deterministic, injectable at
precise model ticks/events, and measurable in detection/recovery latency.

## 2. Fault model

* Faults are **deterministic and reproducible**: same scenario → identical
  ticks, counters, and final state (verified by repetition tests).
* Faults are injected/cleared around explicit `soc_step()` windows
  (`soc_fault_inject` / `soc_fault_clear`, e.g. inject mid-BUSY, step 50,
  assert still BUSY). No wall-clock sleeps, no randomness.
* Faults are **additive latches** on top of the model: default off, so every
  Phase-1–4 test behaves bit-identically with the injector present.
* Detection uses **model-tick budgets** (validation-side timeouts), and
  recovery reuses **existing semantics only** (two-step DMA clear, INTC
  ACK/CLEAR, peripheral reset). No new registers, no new IRQ mechanism.

## 3. Fault taxonomy (intended behavior — defined before implementation)

| Fault | Injection | Intended behavior |
|---|---|---|
| `dma-invalid-src` | Program SRC outside SRAM, START | Synchronous ERROR + ERR_CODE=1, no BUSY phase, no memory touched, IRQ iff enabled at START |
| `dma-invalid-dst` | Program DST outside SRAM, START | Same as above |
| `dma-timeout` (stuck BUSY) | Valid START, then latch stuck-busy | BUSY frozen (countdown suspended), DONE never sets; validation budget expires → detect; abort via `dma.reset()` + re-init + two-step clear → idle |
| `uart-stuck-busy` | TX, then latch stuck-busy | STATUS stays BUSY, RX_VALID never sets, no completion IRQ; validation budget expires → detect; clear latch → completes normally |
| `irq-storm-timer` | N rapid TIMER raises pre-ACK | PENDING coalesces to one bit; exactly one logical ACK; IRQ_COUNT +1; priority intact |
| `irq-storm-mixed` | UART + TIMER + DMA pending together | ACK order strictly 1, 2, 0; unrelated bits never cleared |
| `mmio-unmapped-read/write` | Access 0x30000000-class address | `SOC_ERR_BUS` + STALLS +1 (spec §3) |
| `mmio-ro-write` / `mmio-wo-read` | Illegal direction access | `SOC_ERR_BUS` + STALLS +1 (spec §3) |
| `mmio-bad-offset` | Valid base + invalid offset | `SOC_ERR_BUS` + STALLS +1 |
| `timer-reset-pending` | `reset_peripherals()` while TIMER IRQ pending/fired | All peripherals return to documented reset values; PENDING/ACTIVE cleared; software re-inits and resumes |
| `reset-during-dma` | `reset_peripherals()` while DMA BUSY | DMA returns to idle (BUSY/DONE/ERROR cleared); partial transfer discarded; software re-runs and completes |

Out-of-range `INTC.CLEAR` writes remain ignored (no fault), clearing an
inactive line stays a no-op, and nested/preemptive IRQ behavior is *not*
introduced — storms queue per the documented non-preemptive semantics.

## 4. Injection mechanism

Faults latch directly in the peripheral models (`fault_stuck_busy` flags
in the UART/DMA structs, default off, so all other tests behave
identically); tests set/clear the latch around explicit step windows and
assert the frozen behavior plus recovery. Detection uses tick budgets
(validation-side step counts); recovery reuses existing semantics only
(two-step DMA clear, INTC ACK/CLEAR, `soc_reset_peripherals`). No
framework, no new registers, no new IRQ mechanism.

## 5. Recovery model (validation level)

Small explicit state machine, not a safety framework:

```text
NORMAL → FAULT_DETECTED → RECOVERY → RECOVERED
                              ↘ UNRECOVERABLE
```

Each run records `current_state, fault_type, fault_time (measured),
detection_time (measured), recovery_time (measured), final_state`, with
latencies derived by subtraction. Recovery never invents hardware: DMA abort
= `soc_reset_peripherals()` + re-init + two-step clear; UART = unlatch +
drain; storms = ordered ACK drain; resets = re-init per the existing reset
contract.

## 6. Measurement methodology

```bash
ctest --test-dir build -R test_faults --output-on-failure
```

The `test_faults` CTest gates the fault classes behaviorally:
latching `dma-timeout` freezes a BUSY transfer mid-countdown (still BUSY
after 50 ticks, DONE after unlatch + step); `uart-stuck-busy` holds BUSY
across 20 ticks and completes after unlatch; invalid DMA fails
synchronously with the destination guard intact. Timeout budgets
are modeled parameters: DMA timeout 76 ticks (4x the healthy 64B
transfer), UART stuck 20 ticks (4x UART latency).

The former 11-case x 5-rep = 55-run Python matrix (`benchmarks/
fault_injection.py`, `validation/faults/`) was removed in the pure-C
migration; its results are archived below unchanged, since the model
semantics they measured are identical in `soc_c`.

## 7. Results

REAL OBSERVATIONS — archived Python-harness matrix (`configs/base.yaml`,
5 reps per fault, bit-identical across reps):

| fault | det (ticks) | rec (ticks) | final | irq total | origin of IRQs |
|---|---|---|---|---|---|
| dma-invalid-src | 2 | 0 | 5x RECOVERED | 5 | 1/run: synchronous ERROR IRQ (enabled) |
| dma-invalid-dst | 2 | 0 | 5x RECOVERED | 0 | none (IRQ not enabled in this case) |
| dma-timeout | 76 | 0 | 5x RECOVERED | 5 | 1/run from the post-recovery health transfer, not the fault |
| uart-stuck | 20 | 5 | 5x RECOVERED | 0 | UART completion IRQ arrives only after recovery; harness drains via STATUS |
| irq-storm-timer | 20 | 0 | 5x RECOVERED | 5 | 1/run: single coalesced ACK |
| irq-storm-mixed | 5 | 0 | 5x RECOVERED | 15 | 3/run: ordered ACKs 1, 2, 0 |
| mmio x5 cases | 0 | 0 | 5x RECOVERED each | 0 | none; each rejection adds 1 STALLS tick |

Reset cases (harness-verified): `timer-reset` det 0 / rec 4 ticks (re-fire
LOAD=4); `reset-during-dma` det 0 / rec 319 ticks (full 1KB re-transfer).
`destination_match` true in all 55 runs; guard words intact; boot benchmark
unchanged at 5 ticks.

## 8. Observed failure/recovery behavior

* REAL OBSERVATION: invalid DMA addresses fail synchronously (ERROR +
  ERR_CODE=1, no BUSY phase) and never touch SRAM — guards and destination
  regions read back intact.
* REAL OBSERVATION: stuck faults freeze exactly one thing (DMA countdown /
  UART busy bit); everything else keeps stepping (ticks advance, timers
  fire), which is why budget-based detection works.
* REAL OBSERVATION: storms coalesce — 10 timer periods in 20 ticks yield one
  pending bit and one counted ACK; mixed-storm ACK order is always 1, 2, 0
  and each ACK leaves unrelated pending bits intact.
* REAL OBSERVATION: aborts are combinational in this model (recovery
  latency 0 for register-clear recoveries); only re-executed work costs
  ticks (UART re-complete 5, DMA 1KB re-run 319).
* MODEL BEHAVIOR: recovery latency 0 must not be read as “instant silicon
  recovery” — MMIO writes cost no ticks in this model by design.
* DERIVED METRIC: latencies are tick subtractions; speedups/avoidance are
  not computed here because fault runs have no happy-path baseline per run
  (see Phase-4 docs for the performance baseline).

## 9. Limitations

* Stuck faults are single-latch freezes, not degraded-performance modes;
  there is no flaky/intermittent fault class.
* Detection budgets are chosen, not learned; a too-small budget would false-
  positive on a slow healthy transfer (budgets appear as plain step counts
  in the tests, so this is auditable).
* As throughout: model ticks only — no silicon conclusions.

## 10. Virtual-model disclaimer

Repeated for emphasis: host-native behavioral model; tick counts and
latencies characterize *this model under the stated config*, not any
physical SoC. Do not quote these numbers as hardware data.
