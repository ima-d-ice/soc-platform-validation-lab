# Interview Prep — SoC Platform & Pre-Silicon Validation Lab

> How to use this file: Part A is what you *say*. Part B is what you *know*
> (every file, function by function). Part C is every number and what it
> proves. Part D is sparring. All `file:line` refs are against `main` after
> Phase 8 (`96c0ef6`). All tick counts are **virtual-model ticks**, never
> hardware timing — say that sentence out loud in every interview.

---

# PART A — THE NARRATIVE

## The 30-second version

“Developed a host-native behavioral SoC platform with C firmware/drivers,
MMIO peripherals, interrupts, DMA, RTOS scheduling and Linux-facing device
interaction; built automated validation and performance benchmarks for
latency, throughput, scheduling and fault-recovery analysis.”

## The 2-minute version

“The problem is real: SoC software is written before silicon exists, so I
built a small deterministic virtual SoC — CPU, memory map, UART, timer,
DMA, interrupt controller, performance counters — plus C firmware and
drivers against a generated register header. On top I modeled FreeRTOS
scheduling semantics and a Linux-facing driver layer, then built pytest
validation (98 tests) and six benchmark harnesses. Findings inside the
model: CPU copy costs 3 ticks/word, DMA burst scaling 8191→4351 ticks on
16KB, priority swap halving RTOS latency 107→57 ticks, storms coalescing
with strict 1-2-0 ACK order, all 55 fault runs recovering byte-identical.
Everything is deterministic — identical scenario, identical numbers.”

## The 5-minute version

Add: (1) why host-native not Verilog — the career track is platform
software/firmware/validation, not RTL; (2) the honesty architecture —
measured vs derived vs modeled on every metric; (3) two real bugs found
by the harness itself (mutex immediate-take missing result; post-START
SRC corruption escaping the tick loop → ERR_ADDR fix); (4) the three
deliberate non-goals — no FreeRTOS kernel vendored (wall-clock would kill
determinism), no kernel driver (userspace model, stated), no 64KB single
transfers (SRAM fit check refuses); (5) one commit per phase, results
gitignored but reproducible.

## Honesty rules (memorize these)

1. Never say ARM/MCU/silicon timing, bus bandwidth, or interrupt latency.
   Say “within the virtual SoC timing model” / “in the configured
   behavioral model.”
2. Never call `rtos/` the FreeRTOS kernel — it *models FreeRTOS scheduling
   semantics* (documented gap list: no SysTick HW, no ISR preemption, no
   priority inheritance, zero-cost context switches).
3. Never call `linux/` a kernel driver — *userspace platform model*,
   no syscalls/headers/IOMMU/caches.
4. Every metric is labeled: **measured** (ticks/counters/registers read
   from the model), **derived** (arithmetic on measured), **modeled**
   (chosen parameters: waits, budgets, workloads).
5. Never claim “DMA/polling/IRQ is inherently faster” — report the
   measured tradeoff in this model (here: identical ticks, reads-vs-IRQs).

## Repo map (say it from memory)

```text
soc/           bus, memory, cpu, uart, timer, interrupts, dma, perf, faults, soc(top)
firmware/      C: boot, drivers(uart/timer/intc/dma/mmio), apps/main, include/, rtos(note)
rtos/          deterministic scheduler modeling FreeRTOS semantics + 4 tasks
linux/         userspace driver: mmio layer, driver, app API
validation/    boot, dma, interrupts, faults, benchmark, rtos, linux, stress
benchmarks/    boot_time, cpu_vs_dma, fault_injection, rtos_scheduling,
               linux_platform, final_matrix
tools/         reggen, plot_dma/faults/rtos/linux, final_report, final_plots, report
configs/       base.yaml (golden), fast_mem.yaml, regs.yaml (header source)
docs/          soc-spec, dma-optimization, fault-injection, rtos,
               linux-platform, experiments, limitations (+ this file)
results/       gitignored JSON + plots (reproducible via documented CLIs)
```

## Git history (one commit per phase — know the order)

1. `7a03150` skeleton + spec — 2. `04a6db6` INTC complete + UART RX IRQ —
3. `a590ba2` DMA burst + completion/error IRQ — 4. `7d53c40` CPU-vs-DMA sweep —
5. `11b5ef6` Phase-4 optimization study — 6. `4c61c9b` fault injection —
7. `346398d` RTOS scheduling — 8. `d6d1aee` Linux platform layer —
9. `96c0ef6` final matrix + portfolio.

## Base config (configs/base.yaml — memorize)

100 MHz (informational only); `ram_latency_ticks: 2`, `rom: 1`;
`dma_burst: 4`, `dma_latency_per_word_ticks: 1`; `uart_latency_ticks: 5`;
SRAM 64KB @0x10000000, ROM 16KB @0x00000000; UART/TIMER/DMA/INTC/PERF at
0x20000000/1000/2000/3000/4000. IRQ lines: UART 0, TIMER 1, DMA 2;
priority TIMER > DMA > UART, non-preemptive, queued.

---

# PART B — CODE WALKTHROUGH (block by block)

## B.1 `soc/bus.py` (5 lines)

* Line 5 `class BusError(Exception)` — the single illegal-access signal for
  the whole platform. Purpose: every bad access (unmapped, RO-write,
  WO-read, unaligned, ROM-write, bad offset) raises this; callers
  (`SoC.read/write`) count a STALLS tick per rejection, so error behavior
  itself is measured. Interview point: one exception type keeps the fault
  taxonomy uniform from unit tests to the fault matrix.

## B.2 `soc/memory.py` — `SimpleMemory`

* Line 10 `__init__`: base/size/readonly/name + `bytearray(size)`. Purpose:
  flat backing store for ROM (readonly=True) and SRAM.
* Line 17 `contains`: range check helper — the routing primitive.
* Line 20 `_offset`: bounds-check → raises `BusError` naming the region.
  Purpose: address validation lives here, not scattered.
* Line 25 `read_word` / 31 `write_word`: alignment check (`addr % 4`) then
  little-endian word access; `write_word` refuses ROM. Purpose: enforces
  the spec's word-only MMIO/CPU contract at the lowest layer.
* Line 39/43 `read_bytes`/`write_bytes`: byte-granular path used ONLY by
  the DMA engine (memmove at completion). Purpose: this asymmetry is why
  the spec says “SRAM supports byte access via DMA model only.”
* Line 49 `load_words`: boot-time ROM image load that *bypasses* readonly
  (initial image install, not a runtime write). Line 57 `zero`: `.bss`.
  Purpose: `SoC.boot` uses exactly these two — ROM load + SRAM zero.

## B.3 `soc/cpu.py` — `Cpu`

* Line 6 `__init__` (pc=ROM base, sp=SRAM top), 14 `reset`, 20
  `enter_main`. Purpose: deliberately minimal — the CPU is a reset/halt/run
  state holder, not an ISA simulator; the study is data-movement and
  control, not instruction execution. Say this proactively: it disarms
  “why no instruction set?” — because the research questions don’t need one.

## B.4 `soc/soc.py` — `SoC` (the top; know cold)

* Line 29 `load_config`: YAML → dict. Purpose: configs are data, so sweeps
  never touch code.
* Line 37 `__init__`: builds ROM/SRAM sizes from config; wires
  `Perf → Intc → Uart/Timer/Dma` dependency order (perf first because
  everyone counts into it; intc before peripherals because they raise
  into it; DMA gets SRAM byte-bridge callables to avoid import cycles).
  Purpose: wiring order IS the hardware block diagram.
* Lines 67–70 byte bridges: DMA ↔ SRAM without circular imports.
* Line 74 `reset_peripherals`: calls each peripheral `reset()` — the
  contract reset-fault tests assert (values restored, SRAM preserved,
  ticks retained: reset ≠ reboot).
* Line 81 `_route`: ROM → SRAM → five MMIO windows. Purpose: single decode
  point; returns None for unmapped.
* Lines 97/124 `read`/`write`: (1) alignment check + stall count, (2)
  `count_mem`, (3) route + dispatch, (4) BusError → stall + reraise,
  (5) unmapped → stall + BusError. Purpose: every transaction is counted
  (MEM_ACC) and every rejection is counted (STALLS) — this is what makes
  “polling costs N+1 reads” and “rejections cost stalls” *measured* facts.
  `write` returns peripheral status (UART TX returns 0 / -1) — the C
  driver’s `UART_ERR_DISABLED` path mirrors this.
* Line 160 `step(n)`: ticks += 1, perf.tick, uart/timer/dma step. Purpose:
  THE model clock — one tick advances all hardware together; the RTOS
  scheduler calls this once per scheduler tick, which is why RTOS and SoC
  share time.
* Line 168 `run_until(predicate, max_ticks)`: poll-a-condition helper
  returning elapsed ticks, TimeoutError on expiry. Purpose: used by every
  completion wait; max_ticks bounds all tests (no hangs, ever).
* Line 181 `boot`: reset CPU/peripherals/counters, enable PERF, optional
  ROM load, SRAM zero, trace reset/main_entry, step BOOT_TICKS=5, return
  measured boot_ticks/ns. Purpose: models Reset→ROM→stack→.data→.bss→main;
  the 5-tick boot number comes from here, measured not asserted.
* Lines 206–209 SRAM word helpers for tests.

## B.5 `soc/uart.py` — `Uart`

* Lines 17–20 status/CTRL bits; line 24 `IRQ_LINE = 0`.
* Line 28 `__init__` takes `latency_ticks` (model: 5), `perf`, `intc`.
* Line 42 `reset`, 51 `_status` (BUSY vs EMPTY are mutually exclusive by
  construction; RX_VALID ORs in).
* Line 61 `read`: TXDATA is WO (BusError), RXDATA returns byte AND clears
  RX_VALID (contract: read-to-clear), STATUS/CTRL/BAUDDIV plain.
* Line 76 `write`: TXDATA while disabled → stall count + return -1
  (`UART_ERR_DISABLED`, bus-legal, no exception — drivers check the code);
  else latch byte + `busy = latency`. CTRL/BAUDDIV stored; RXDATA/STATUS
  writes → BusError.
* Line 97 `step`: countdown; on expiry loop back byte, set RX_VALID, raise
  INTC line 0 unconditionally (delivery gated solely by INTC.ENABLE — no
  per-UART enable bit, map preserved). Phase-5 hook: `fault_stuck_busy`
  freezes the countdown (stays BUSY, never completes, no IRQ) — default
  off, cleared by reset.

## B.6 `soc/timer.py` — `Timer`

* Lines 12–15 CTRL bits (ENABLE/PERIODIC/IRQ_ENABLE), FIRED bit.
* `read`/`write` (34/47): VALUE is RO; IRQ_STATUS is W1C; IRQ_CLEAR is WO;
  CTRL 0→1 latches LOAD→VALUE if VALUE is 0 (the arming semantic).
* Line 73 `step`: disabled → return; LOAD=0 + ENABLE → never fires
  (specified edge case, tested); else decrement; on zero: set FIRED, raise
  line 1 iff IRQ_ENABLE, periodic reloads else auto-disables (one-shot).
  Purpose: one-shot vs periodic + storm source (periodic LOAD=2 is the
  storm generator).

## B.7 `soc/interrupts.py` — `Intc` (know cold)

* Lines 27–34: lines 0/1/2, `PRIORITY_ORDER = (TIMER, DMA, UART)`,
  highest-first. Fixed priority, no priority registers (stated limit).
* Line 44 `reset`, 49 `raise_irq` (idempotent bit-set = coalescing by
  construction: N raises → one bit → one ACK).
* Line 53 `_highest`: `pending & enable & 0x7` scanned in priority order.
  Purpose: ENABLE gates ACK *only* — pending still records while disabled
  (tested by enable-gating test).
* Line 60 `read`: ENABLE/PENDING/ACTIVE plain RO; ACK (the read-to-ack):
  highest line or IRQ_NONE (0xFFFFFFFF); on hit clears PENDING, sets
  ACTIVE, counts one PERF IRQ. Spurious/double ACK → NONE, counts nothing.
* Line 78 `write`: ENABLE masked to 3 bits; CLEAR takes an IRQ *number*,
  out-of-range ignored (no fault), inactive clear is a no-op; writes to
  PENDING/ACK/ACTIVE → BusError. Purpose: the two-step DMA clear
  (DMA.IRQ_CLEAR then INTC.CLEAR) is proven distinct because flag-clear
  leaves INTC pending set.

## B.8 `soc/dma.py` — `Dma` (know coldest)

* Lines 20–30 CTRL/STATUS/ERR codes (BUSY/DONE/ERROR; NONE/ADDR/ALIGN/LEN).
* Line 48 `__init__`: bounds, `latency_per_word`, `burst` (config-only —
  no BURST register, map preserved), intc/perf refs, SRAM bridge callables.
* Line 75 `reset` (also clears stuck latch), 89 `_in_sram`.
* Line 95 `read` / 119 `write`: SRC/DST/LEN/CTRL RW; STATUS/ERR_CODE RO;
  IRQ_CLEAR WO; START is write-1-to-start then auto-cleared in the stored
  CTRL word.
* Line 145 `_fail`: no BUSY phase — ERROR + code immediately, IRQ iff the
  latched enable was set. Purpose: synchronous validation errors.
* Line 153 `_start`: BUSY re-START ignored + stall counted; latch IRQ_EN;
  clear sticky flags; validate LEN→ALIGN→ADDR in that order (code priority
  is deterministic); then BUSY + `_remaining = words*lat + (bursts-1)`,
  bursts = ceil(words/burst). Purpose: this formula IS the burst study.
* Line 177 `step`: not-busy → return; **stuck latch → frozen BUSY**;
  else countdown; at zero, memmove via snapshot (overlap-safe), BUSY→DONE,
  `count_dma(length)`, raise line 2 iff latched. **Phase-7 fix**: the
  reader/writer pair sits in try/except BusError → converts a post-START
  address change into ERROR/ERR_ADDR + IRQ instead of escaping the tick
  loop (uncaught exception out of `SoC.step` was the genuine bug the
  harness found; spec §5.3 documents it).

## B.9 `soc/perf.py` — `Perf`

* Lines 35–53 `tick/count_mem/count_stall/count_dma/count_irq` — ALL gated
  on `enabled` (so boot/reset sequencing matters and is tested).
* Lines 56/71 MMIO: counters RW (write-to-set, incl. zeroing); CTRL bit0
  ENABLE, bit1 RESET (write-1 zeroes all). Bad offset → BusError. Purpose:
  every “measured” number in every table comes out of these five counters
  plus `soc.ticks`.

## B.10 `soc/faults.py` — injector + recovery machine

* Line 31 `Fault`: name + params + optional `at_tick` / `event` predicate.
* Line 40 `RecoveryTracker`: NORMAL→FAULT_DETECTED→RECOVERY→RECOVERED/
  UNRECOVERABLE with `_go` enforcing legal edges (illegal jumps raise —
  tested); `detection_latency`/`recovery_latency` are DERIVED subtractions;
  `record()` emits the row fields the benchmark JSON uses.
* Line 115 `FaultInjector(soc)`: 124 `inject` (applies latch + marks
  active), 129 `clear` (unlatches; unknown name is a no-op), 135
  `is_active`, 139 `apply_at_tick` / 144 `apply_at_event` (schedule),
  149 `poll` (call after every `soc.step`; fires due faults; event
  exceptions are swallowed to stay deterministic), 171 `_apply_latch`
  (dma-timeout → `dma.fault_stuck_busy`, uart-stuck-busy → UART latch;
  stimulus faults need no latch — tests drive them via MMIO; unknown
  latch name asserts).

## B.11 `rtos/kernel.py` — scheduler (know cold; bugs found here)

* Line 23 `WorkItem(seq, birth, deadline, payload)` — the dated unit of
  work; birth/deadline ticks make latency and misses computable.
* Line 30 `RtosQueue`: bounded deque + `try_send/try_recv` (never block
  internally — blocking lives in the scheduler); stats sends/receives/
  drops (timeout==0 refusal)/send_timeouts/recv_timeouts/max_depth.
  Purpose: drops vs waits are separately counted, which is what makes the
  queue-depth tradeoff (19→0 drops vs 0%→87.5% misses) a measured both-sides
  result.
* Line 72 `RtosMutex`: non-recursive, owner + takes + contentions; handoff
  to highest-priority waiter on give. **No priority inheritance** —
  documented gap, say it before they ask.
* Line 82 `Task`: name/priority/generator/scheduler + `compute_remaining`,
  `wake_at/wait_kind`, `next_wake` (delay_until anchor), notify mailbox,
  `run_ticks` (starvation analysis input), `wake_log` (expected vs actual).
* Line 103 `Scheduler(soc)`: `now`, task table, `context_switches`,
  `idle_ticks`, `_last_run`, `_rr` tie-breaker list.
* Line 117 `create_task` (duplicate names assert), 125 `notify`
  (overwrite + count — overwrite loss is observable via notify_count).
* Line 131 `tick`: now+=1 AND `soc.step(1)` — the shared-clock decision
  (RTOS and peripherals advance together); `_progress_blocked`; pick
  highest-priority READY (ties rotate via `_rr`); count a switch only when
  the runner actually changes (first run counts nothing); append run tick;
  `_run_task`. Empty ready set → idle tick (utilization denominator).
* Line 155 `run(ticks)`; 160 `_progress_blocked`: delays/delay_until wake
  (delay_until logs expected/actual/missed into `wake_log` — the jitter
  source); qsend succeeds-or-times-out (timeout==0 → drops++ and immediate
  False); qrecv item-or-timeout; notify_wait value-or-timeout; mutex_take
  free-or-timeout. Purpose: all blocking lives here, retried once per tick.
* Line 231 `_run_task`: bounded loop (MAX_STEPS_PER_TICK=32 anti-runaway);
  compute-holder decrements one unit per scheduled tick (preemption just
  leaves `compute_remaining` for later — no holder state needed); fresh
  tasks advance with stored result. **Bug found here #1**: the consumed
  result was wiped by `t.result = None` *after* `_advance`, so an
  immediately-completing op’s result never reached the generator — fixed
  by consume-first (`res, t.result = t.result, None`).
* Line 254 `_advance`: first call `next(gen)`, later `gen.send(value)`
  (tracked by `Task._started` class-flag shadowed per instance);
  StopIteration → finished. **Bug found here #2 (via mutex test)**:
  immediate mutex-take success never set `t.result`, so the worker got
  `send(None)` and asserted — fixed by setting `t.result = True` on the
  fast path. Interview gold: “my tests found two scheduler bugs.”
* Line 264 `_exec_op` per op: compute sets `remaining=n` (the run loop
  consumes exactly n ticks — verified: proc-4 latency is exactly 6 =
  proc 4 + telem 2); delay wakes at now+n; delay_until anchors
  `next_wake` with overrun catch-up (`now+1`, the P-10 jitter source);
  qsend/qrecv/notify/mutex as above with timeout None = forever, 0 =
  non-blocking; `now` op returns the model clock (how tasks timestamp
  births); unknown op asserts (fail-fast, no silent miss).

## B.12 `rtos/tasks.py` — the four tasks

* Line 17 `acquisition_task`: delay_until(period) → optional compute →
  read clock → build WorkItem(birth=now, deadline=now+D) → qsend
  timeout=0 (full queue = counted drop, producer never blocks — the
  pressure valve). `max_items` bounds benchmark runs; infinite otherwise.
* Line 41 `processing_task`: qrecv forever → compute(cost) → qsend with
  send_timeout=50 (bounds the forward path; drops counted, no deadlock).
* Line 56 `telemetry_task`: qrecv → compute(tx) → read clock → latency =
  now − birth, miss iff now > deadline. Purpose: the single latency/miss
  observation point for the whole pipeline.
* Line 72 `diagnostic_task`: lowest priority, periodic, samples per-task
  max run-gaps. Purpose: starvation made visible as data (diag itself
  starves first — check the `starved` columns).

## B.13 `linux/` — userspace driver model (say “not a kernel driver” first)

* `mmio.py` line 34 `DeviceRegs`: the ONLY address-knowing layer (DMA/INTC
  constants mirror the SoC map); `dma_program` writes SRC/DST/LEN/CTRL in
  one call; irq helpers; BusError propagates untouched for the driver to
  translate. Purpose: app/driver never import SoC addresses — the
  hardware/software boundary is a code boundary.
* `driver.py` line 30 `StreamError` (timeout/DMA-error/exhaustion/bad-arg);
  35 `Frame` (handle/size/seed + three timestamps); 46 `Ticket`.
* Line 51 `StreamDriver`: ring_depth, 32KB arena @0x10004000 + 16KB staging
  @0x10000000 (driver-private constants), descriptor deque, single
  `_active` frame (**single channel is a model fact**: at most one engine
  transfer at a time), `max_outstanding` high-water mark, notification/
  poll/timeout/drop/completed counters.
* Line 73 `init` (reset engine, clear IRQ, configure gating, drain stale
  pending), 84 `close`, 92 `abort` (reset + clears + drop all — the
  timeout-recovery primitive), 108 `alloc` (opaque handles, alignment +
  arena/staging fit checks → clean errors, never crashes).
* Line 124 `_fill_staging` (CPU pattern fill `seed^i` — integrity root),
  129 `_engine_idle`, 132 `pump` (START oldest queued frame only when no
  active frame and STATUS fully idle; DONE-with-no-owner raises fail-fast;
  payload filled at START time so queued frames can’t overwrite each
  other — the fix that made depth>1 sound).
* Line 153 `_handle_busy` (buffer reuse guard: submitting to a buffer with
  an outstanding frame counts as ring-full — models real buffer pressure;
  this is why 16KB depth-4/8 rows collapse to depth-2 behavior).
* Line 156 `submit` (blocking w/ tick timeout) vs 178 `try_submit`
  (non-blocking → drop count). 196 `_collect_active` (IRQ path asserts
  pending + ACK==2 then clears and counts notification; polling path
  asserts NO pending — the modes police each other). 214 `wait`
  (pump-aware loop; ERROR → StreamError with code; timeout → count +
  raise). 238 `collect_ready` (paced-consumer reap). 255 `verify`
  (word-compare `seed^i` — integrity proof). 263 `stats`.
* `app.py` line 12 `StreamApp(driver, consumer_period)`: back-to-back
  try_submit producer + paced drain consumer; 22 `_reap` (loop until no
  completion ready — the earlier draft discarded completions here, caught
  in review); 33 `run` returns submitted/dropped/completed/mismatches/
  latencies/notifications/poll_reads. Drops = refused attempts while ring
  full (frames retried → completions == submitted); label exactly that.

## B.14 `firmware/` (C, host-native)

* `include/soc_regs.h` — GENERATED by `tools/reggen.py` from
  `configs/regs.yaml`; never hand-edited (build fails if missing — enforced
  in CMakeLists). Purpose: one source of truth so Python model and C
  drivers can’t diverge on addresses.
* `include/driver_api.h` — MMIO fns + UART/Timer/INTC/DMA/boot APIs with
  negative error codes mirroring the Python model (`UART_ERR_DISABLED`,
  `DMA_ERR_*`). Purpose: the contract both sides code against.
* `drivers/mmio.c` line 35/92: static-table MMIO shim (reset values from
  the spec) so driver *logic* (bit ops, sequencing, error checks) compiles
  and runs on host; line 170 `vlab_mmio_consume_rx` mirrors the model’s
  read-clears-RX_VALID. Purpose: honest split — system behavior lives in
  `soc/`, driver logic is unit-exercised here.
* `drivers/uart.c`: init sets BAUDDIV+ENABLE; `uart_write_byte` checks
  ENABLE, bounded-polls TX_EMPTY (1000), writes TXDATA; `uart_read_byte`
  checks RX_VALID then consumes. `timer.c`: load/CTRL compose, W1C clear.
  `intc.c`: mask/ack/clear passthrough + comment that UART IRQ is gated by
  INTC.ENABLE only. `dma.c` line 12 `in_sram` + 19 `dma_start`: BUSY→LEN→
  ALIGN→ADDR validation order mirrors `Dma._start`, same error codes.
* `boot/boot.c` line 16 `boot_init` (disable IRQs → PERF reset+enable →
  `.data` copy → `.bss` zero → UART init) + line 32 `boot_self_check`;
  `apps/main.c` line 8 `main` (boot → self-check → hello → arm timer).
  Purpose: the Reset→ROM→stack→data→bss→main story as real code.

## B.15 `configs/` — every key’s timing effect

`base.yaml`: `cpu_frequency_mhz: 100` (ns reporting only); `ram_latency`
→ CPU wait (1+2=3 ticks/word); `dma_latency_per_word_ticks: 1` × words;
`dma_burst: 4` → burst overhead term; `uart_latency_ticks: 5` → loopback +
  IRQ delay; `sram/rom_size` → fit checks (16KB cap, 32KB arena math).
  `regs.yaml` → header (addresses/access/reset/descriptions only).
  `fast_mem.yaml` exists for future sweeps, unused by gates (say so).

## B.16 `benchmarks/` — methodology per tool (all: fresh SoC+boot per cell, reps, provenance, gitignored JSON)

* `boot_time.py:20 main`: N boots → ticks/ns/cycles/mem_acc rows + summary
  (min/max/mean/deterministic flag). The 5-tick boot number’s origin.
* `cpu_vs_dma.py`: 86 `_pattern`, 91 `_check_fit` (refuses >SRAM — the
  64KB story), 101 `_snapshot` / 112 `_delta` (counter-delta discipline:
  setup and verification reads sit OUTSIDE snapshots), 116 `measure_cpu`
  (read+write+step(per_word) per word), 153 `measure_dma_polling`
  (START w/o IRQ, STATUS-poll loop counting reads, asserts NO pending),
  202 `measure_dma`→207 `measure_dma_irq` (run_until + PENDING→ACK→clears,
  transfer vs total ticks split), 254 `_with_burst` (config-copy override,
  no register change), 260 `run_cell` (the schema row incl. provenance),
  336 `_summarize` (by_size/burst/mode + crossover = smallest size with
  dma< cpu else the exact string “No crossover observed in tested range”).
* `rtos_scheduling.py`: 38 `_pct`, 46 `_stats_list`, 55 `_jitter` (pstdev),
  61 `_starvation` (max run-gap vs 5×period rule), 72 `run_pipeline`
  (builds SoC+scheduler+queues+4 tasks, runs, returns latencies/periods/
  misses/depths/switches/starvation), 123 `build_scenarios` (16: priority
  pair overloaded, load 1–16, depths 1–16, periods 10/20/40 — each sized
  so scheduling matters; light cases are controls), `main` prints the
  table + determinism flag.
* `linux_platform.py`: 42 `_expected_xfer` (pacing = formula value), 48
  `_frames_for` (byte-budget frame count: max(4, min(32, 65536//size))),
  62 `run_cell` (driver init → alloc capped by arena → app.run →
  mem/dma/irq deltas + e2e stats + throughput + drops + provenance).
* `fault_injection.py`: 72 `_expected_dma_ticks`, 78 `_snap`, 98/103
  pattern+verify, 108 `_finish` (delta math + provenance), 132–372 case
  functions (each: guard/setup → inject at recorded tick → budgeted
  detect → defined recovery → verify → row), `ALIASES`
  (dma-invalid/irq-storm/mmio-invalid expand), `_stats`, `main` (fresh
  SoC per (fault, rep), determinism check, per-fault summary).
* `final_matrix.py`: imports phase helpers directly (F1/F2←cpu_vs_dma,
  F4/F6←linux_platform, F5←rtos_scheduling, F7←fault_injection CASES) —
  F3 is a derived view over F1 rows (no rerun, stated); F8 seven fresh
  stress scenarios (67–160: IRQ-rate loop, 8×16KB pressure, queue/starve
  reuse, comm-timeout with abort+re-latch, 20× invalid access, 5×
  mid-DMA reset); 193 `_dominant` (largest-share bottleneck rule);
  bottlenecks dict. Purpose: cross-phase comparability by construction.

## B.17 `tools/` + `validation/` map

* `reggen.py:28 main`: regs.yaml → header + bit defines; fails loudly
  without PyYAML. `report.py`: JSON→markdown table. Plotters
  (`plot_dma/faults/rtos/linux`, `final_report`, `final_plots`): Agg
  backend (headless-safe), rep-0 or rep-mean selection, fail loudly on
  missing/empty data; 8+7+7+6+8 = 36 PNGs, all from real JSON (never
  sketch a plot — the “no fabricated plots” rule, enforced by loaders).
* `validation/`: `conftest.py` (config/soc/fresh_soc fixtures); `boot/`
  (boot flow, UART loopback/timing/disabled-TX, bus-error matrix);
  `interrupts/` (timer fire/periodic/zero-load, INTC gating/ack/active/
  spurious + double-ack/invalid-clear, 3-way priority + storm coalescing);
  `dma/` (completion, error codes, busy-ignore stalls, burst timing +
  sensitivity, two-step clear, overlap memmove, DONE-sticky, cpu_vs_dma
  helpers); `faults/` (6 files: invalid/timeout+tracker, UART stuck,
  storms, MMIO matrix, mid-activity resets, recovery-machine transitions
  incl. illegal-edge rejection); `benchmark/` (optimization schema +
  no-faster-assumption test via synthetic slow-DMA rows); `rtos/` (core
  primitives + system: preemption order, deadlock-free drain, corruption-
  free 50-item run, miss/starvation detection, repeat determinism,
  priority-swap divergence); `linux/` (init gating, register readback,
  both-mode integrity, arena exhaustion, notification-vs-poll counts +
  equal transfer ticks, fault-injected timeout→abort→idle, post-START
  corruption→StreamError, app determinism); `stress/` (placeholder READMEs
  for deferred sweeps — say so if asked).

# PART C — METRICS ENCYCLOPEDIA (every number, labeled)

Label key: **[M]** measured (read from model) · **[D]** derived (arithmetic)
· **[O]** modeled (chosen parameter).

## C.1 The five PERF counters + ticks (all [M], `soc/perf.py`)

| Counter | Increment site | Counts | Observed examples |
|---|---|---|---|
| `soc.ticks` | `soc.py:160` every `step` | model time itself | boot=5; 64B DMA=19; 16KB burst4=5119 |
| CYCLES | `perf.tick`, gated on enable | ticks while enabled | == ticks post-boot (enabled at boot) |
| MEM_ACC | `soc.read/write` via `count_mem` | every bus transaction incl. rejected-op attempts | 64B CPU path 32, DMA-irq path 29 |
| STALLS | `count_stall`: BusError paths, UART-disabled-TX, DMA BUSY re-START | rejection/busy waits | 20/20 invalid accesses → 20 |
| DMA_BYTES | `dma.step` completion | payload bytes moved | == transfer size on success |
| IRQ_COUNT | `intc.read` ACK hit | valid ACKs only (spurious/double = 0) | mixed storm = 3/run |

## C.2 DMA formula terms (`soc/dma.py:153–177`)

`words = LEN/4` [O input]; `bursts = ceil(words/burst)` [D];
`ticks = words*lat + (bursts−1)` [M — the countdown actually stepped].
Spot values (lat=1): 16B/b4 = 4+0 = **4**; 64B/b1 = 16+15 = **31**,
b4 = 16+3 = **19**, b16 = 16+0 = **16**; 16KB/b4 = 4096+1023 = **5119**,
b1 = **8191**, b16 = **4351**. CPU copy = 3 ticks/word [O wait + M steps]:
16B=12 … 16KB=12288. Speedup converges ~2.40x @b4, ~1.50x @b1, ~2.83x @b16 [D].

## C.3 CPU-vs-DMA row fields (`benchmarks/cpu_vs_dma.py:260`)

`cpu_ticks`/`dma_transfer_ticks`/`total_ticks` [M]; `setup_ack_ticks` =
total−transfer [D] (== 0 everywhere — MMIO combinational [O]);
`mem_accesses`/`irq_count`/`stalls`/`dma_bytes` [M deltas];
`throughput`/`transfer_throughput`/`speedup_vs_cpu` [D];
`cpu_work{bus_ops}` [M] vs `cpu_work_avoided_bus_ops` [D subtraction —
never call it a hardware probe: −6 @16B … +3063 @16KB];
`completion_cost{status_reads}` [M loop count: polling N+1, irq exactly 3];
`destination_match` [M assert]. Crossover [D rule]: smallest size with
dma < cpu else the “No crossover…” string (here: 16B everywhere — report,
don’t extrapolate below).

## C.4 RTOS stats (`benchmarks/rtos_scheduling.py:38–70`)

`latencies`/`periods`/`misses`/`depths`/`drops`/`ctx`/`runs` [M];
`mean/p50/p99/max` [D nearest-rank]; `jitter` = pstdev(actual periods) [D];
`miss_rate` [D]; starvation = max run-gap > 5×period [M gaps vs O rule].
Observed: prio swap 107.17/135 → 57.07/72 (mean/p99), ctx 99→118, tele
starves only under proc-high; load lat == proc+2 exactly, 100% miss from
proc-8 (deadline 9); queues drops 19→0 vs miss 0%→87.5%, max_depth ==
capacity every row (saturation proof); P-10 jitter 1.43 + 100% miss,
P-20/40 jitter 0.00.

## C.5 Linux row fields (`benchmarks/linux_platform.py:62`)

`completion_ticks` = mean per-frame e2e [M]; `e2e_stats` latencies+p99
[M+D]; `total_ticks`, `throughput` = moved/total [D]; `queue_depth` =
max_outstanding [M]; `drops` = refused submits, frames retried so
completed == submitted [M — label backpressure, not loss];
`notifications` [M: 1/frame irq, 0 polling], `poll_reads` [M: N+1/frame];
`mismatches` [M: 0 in all 200 cells]. Observed: depth-1 halves throughput
(~1.6 vs ~3.2); e2e grows with depth (64B: 36.4→134.6); 16KB b4/b8 rows
collapse to depth-2 (arena cap — documented, visible as flat lines).

## C.6 Fault row fields (`benchmarks/fault_injection.py:108`)

`injection/detection/recovery_point` [M ticks]; latencies [D
subtractions]; `final_state`, `dma_status`, `uart_status`, `pending_irqs`,
`active_irq`, `irq_count`, `mem_accesses`, `stall_count`,
`destination_match` [M]; `timeout_budget_ticks` [O, recorded per run].
Observed (means, 5 reps, min==max everywhere): invalid src/dst det 2 /
rec 0; timeout det 76 / rec 0; uart-stuck det 20 / rec 5; timer-storm det
20 / rec 0 (1 IRQ); mixed-storm det 5 / rec 0 (3 IRQs, order 1-2-0); all
five MMIO det/rec 0; reset-during-dma rec 319 (full 1KB re-run); all 55
runs RECOVERED, match true. Recovery-0 rows are register-clear aborts
([O] combinational MMIO) — say the caveat with the number.

## C.7 F8 stress + bottlenecks (`benchmarks/final_matrix.py`)

250/250 storm IRQs @50/100 ticks; 8×16KB sustained 3.2006 B/tick [M];
queue-pressure 19 drops/40 completions; starvation tele 32 vs proc 602
runs; 3/3 timeouts + idle-after-abort true; 20/20 rejections + 20 stalls;
5/5 reset recoveries. Bottlenecks [D largest-share rule]: dma-* =
transfer 1.00 (setup_ack 0 — the combinational-MMIO caveat, stated
alongside); queue-pressure = completions 0.68. p50/p95/p99 via `_pct`
nearest-rank [D]; never mix semantics — m1 plots only single-transfer
ticks, m2 warns definitions differ, m8 log-scales labeled mixed units.

# PART D — Q&A BANK (with model answers)

## Hostile / framing questions

**Q: “Isn’t this just a Python simulator? Why should we care?”**
A: “It’s a behavioral platform model with a purpose: deterministic
firmware and validation development before silicon. The value isn’t cycle
accuracy — it’s that 98 tests and six benchmark suites run bit-identically
every time, so every scheduling, burst, buffer, and fault effect is
attributable. That’s the pre-silicon workflow: develop and characterize
against the model, then validate assumptions on hardware.”

**Q: “Why didn’t you use real FreeRTOS / write a real kernel driver?”**
A: “Deliberate tradeoff, documented in `docs/rtos.md` and
`docs/linux-platform.md`. A wall-clock FreeRTOS port would destroy the
determinism guarantee the whole study rests on — I model the scheduling
semantics instead and list the gaps honestly: no SysTick HW, no ISR
preemption, no priority inheritance, zero-cost switches. Same for Linux:
a userspace layering model validates driver *structure* — completion
paths, error handling, buffer discipline — without pretending to be
kernel code.”

**Q: “Your speedups are made up.”**
A: “Every number traces to `soc.ticks` or a PERF counter read, with the
formula in `soc/dma.py:153–177` and `docs/soc-spec.md`. Reps are
bit-identical — check `deterministic_across_reps` in any result JSON, or
rerun the CLI. Modeled parameters (3 ticks/word, burst overhead, budgets)
are recorded per run, never hidden.”

**Q: “What would break first on real hardware?”**
A: “Three things I state in the report: combinational MMIO makes setup/ACK
and register-clear recovery read 0 ticks — real entry/exit and bus costs
are non-zero, so polling-vs-IRQ and recovery-0 rows would shift; zero-cost
context switches flatter small-work scheduling differences; and there’s no
contention, caches, or concurrent masters, so all throughput numbers are
upper bounds of this model, not predictions.”

## Architecture questions

**Q: “Walk me through a DMA completion IRQ end to end.”**
A: “Driver writes SRC/DST/LEN then CTRL with START+IRQ_EN (`linux/mmio.py:
dma_program`). `Dma._start` validates, latches IRQ_EN, sets BUSY with
`_remaining = words*lat + (bursts−1)`. Each `SoC.step` ticks the countdown;
at zero it memmoves SRAM→SRAM, sets DONE, counts DMA_BYTES, raises INTC
line 2. The IRQ path reads PENDING, ACKs (PENDING→ACTIVE, IRQ_COUNT++),
then two-step clears: DMA.IRQ_CLEAR for flags, INTC.CLEAR for the active
bit. 64B/burst-4: 19 ticks, verified byte-identical.”

**Q: “Why two-step clear? Why not one register?”**
A: “Because two independent states exist: the peripheral’s sticky DONE
flag and the controller’s pending/active bits. Clearing only DMA flags
leaves INTC pending set — proven by test, which asserts PENDING survives
the first step. That mirrors real HW (peripheral flag vs NVIC pending)
and it’s why the ordering contract is tested, not just documented.”

**Q: “Why does ACK read-to-clear instead of write-1-to-clear?”**
A: “Atomicity: the read both selects the highest pending+enabled line and
moves it to ACTIVE, so a storm raising lines mid-drain can’t be lost or
double-counted. Coalescing falls out of the bit-set design.”

**Q: “Fixed priority — why no programmable priorities?”**
A: “Scope discipline: the studied questions (ordering under storms,
starvation victims) need *a* deterministic order, not a programmable one.
Priority registers would add surface without new insight; documented as a
limit, and the fixed order TIMER > DMA > UART is asserted by 3-way tests.”

## Findings questions (answer with numbers)

**Q: “Strongest DMA result?”** — Burst 1→16 cuts 16KB 8191→4351 ticks;
gains saturate at one burst; formula verified tick-exact across 300 cells.
**Q: “Polling vs IRQ — which wins?”** — “Neither on time: identical ticks
everywhere in this model. The tradeoff is attention: N+1 STATUS reads vs
1 IRQ + 3 MMIO ops, +2 MEM_ACC per transfer. On hardware the answer would
differ — that’s stated.” **Q: “Priority inversion?”** — “No inheritance
in the model (stated gap). What I measured instead is priority *effect*:
identical overload, 107.2 vs 57.1 mean ticks, telemetry starved only under
proc-high.” **Q: “Queues?”** — “Both sides measured: depth 1→16 drops
19→0 while miss rate 0%→87.5%. Neither deep nor shallow is ‘better’ —
that’s the tradeoff curve.” **Q: “Faults?”** — “Synchronous invalid-DMA
failure with zero corruption (det 2); budget-caught stalls (76/20);
storms coalesce with order 1-2-0; 55/55 RECOVERED byte-identical; no
UNRECOVERABLE instance exists — branch unit-tested only, say so.”

## Process questions

**Q: “How do you know the model is right?”** — “Three ways: contract
(`soc-spec.md` + generated header = single source of truth), validation
(98 tests incl. determinism re-runs and no-faster-assumption tests), and
the harness finding real bugs (two scheduler bugs, one DMA completion
fault path). Tests found bugs — that’s the credibility story.”
**Q: “Why one commit per phase?”** — “Reviewable history mirroring how
platform software lands: contract → mechanism → measurement → hardening.
Results never committed (gitignored), code always green at each commit.”

## Whiteboard prompts (practice these)

1. Draw the full stack (app → scheduler/driver → HAL → SoC → harness) and
   point at where time comes from (shared tick clock).
2. Trace `try_submit` → `pump` → START → DONE → `collect_ready` → `verify`
   on the whiteboard, naming every tick-consuming step.
3. Given LOAD=2 periodic timer + 20 idle ticks, compute pending/ACK/IRQ
   counts by hand (answer: 1 bit, 1 ACK, +1 IRQ).
4. Given 1KB, burst 8, lat 1: compute transfer ticks (256 words, 32
   bursts → 256+31 = 287).
5. Explain why `setup_ack_ticks` is 0 and why that’s a model artifact.

*End. Re-verify any `file:line` you quote against `main` before the
interview — refs drift as code evolves.*

## Addendum — C pivot (firmware deepened after Phase 8)

* `firmware/include/hal.h` + `hal/hal.c`: volatile `read_reg`/`write_reg`,
  `set/clear/modify_bits`, `irq_disable/restore` (host: nesting counter;
  silicon path: PRIMASK asm, compiled only without `VLAB_HOST_SIM`).
  All drivers refactored onto it — say “one door for all register access.”
* `firmware/include/isr.h` + `isr/isr.c`: vector table, `isr_register`,
  bounded `isr_dispatch` (ACK → handler → CLEAR, unregistered lines still
  cleared so nothing wedges). Dispatched on host, stated openly.
* `drivers/dma.c`: interrupt-driven lifecycle
  IDLE→STARTING→ACTIVE→COMPLETE→ERROR→RECOVERY with volatile flags,
  critical sections, two-step clear inside the ISR; `dma_is_complete()`
  polls the flag with zero bus traffic.
* `drivers/mmio.c` now emulates INTC ACK priority + BUSY-on-START and
  exposes `vlab_test_*` hooks (tests/demo only) — say exactly that.
* `apps/isr_demo.c`: ordered bring-up with failure codes, complete leg,
  forced-error leg, recovery leg, `DEMO OK` gate in CTest.
* CTest now 5 suites: smoke, `hal_unit`, `drivers_unit`, `isr_unit`,
  `isr_demo_fw`. New volatile/ISR/race interview material is in
  `docs/firmware-c.md` (“Interview map”).
