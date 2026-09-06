# Firmware in C — what is real and what is host behavior

The C side (`firmware/`) is genuine embedded firmware structure compiled
with `-Wall -Wextra -Werror` (C11): a HAL, four drivers (UART, timer,
INTC, DMA), a dispatched ISR framework, platform bring-up, a demo app,
and CTest suites (`test_hal`, `test_drivers`, `test_isr`,
`test_dma_integration`, `test_dma_faults`, `firmware_smoke`).

## What is real C

* **HAL** (`hal/hal.c`, `include/hal.h`): `read_reg`/`write_reg` as
  volatile-qualified accesses, `set/clear/modify_bits` RMW helpers,
  `irq_disable/restore` critical-section structure. All drivers use it;
  nothing touches `vlab_mmio_*` outside HAL/mmio.
* **Driver logic**: validation ordering (BUSY→LEN→ALIGN→ADDR, mirroring the
  `soc_c` model), bit composition, W1C handling, error codes,
  bounded poll loops with timeout returns.
* **DMA is an endpoint-to-endpoint engine**: the driver identifies source /
  destination kinds (MEM vs listed peripheral FIFOs), checks roles
  (uart-tx is sink-only, uart-rx source-only) and then the configured
  direction caps. Invalid API use (LEN/ALIGN/ADDR) is distinct from
  platform refusal (UNSUPPORTED: incapable endpoint, wrong role,
  disallowed direction, over max). VLAB's three enabled directions are one
  platform choice (`firmware/platform/`), never a universal rule.
* **ISR discipline**: vector table + registration (`isr.c`), volatile
  ISR/main shared flags, critical sections around submit/recover state
  transitions, ACK-then-clear ordering inside the ISR, bounded dispatch so
  a babbling source cannot livelock the loop.
* **State machines**: DMA lifecycle
  `IDLE→STARTING→ACTIVE→COMPLETE→(recover)→IDLE` /
  `ACTIVE→ERROR→(recover)→IDLE`. Illegal transitions are
  rejected (submit requires IDLE; recover acts only from terminal states).
* **Init sequencing** (`platform/platform_init.c`): ordered bring-up with
  failure propagation — later stages never run on an earlier failure.

## What is host behavior (stated, not hidden)

* **Registers, one live model**: every HAL access routes through the host
  bridge into the ticking SoC engine (reset values, W1C, START-self-clear,
  UART latency, timer countdown, DMA bursts, fixed INTC priority), stepped
  explicitly by tests and apps. There is no second shim: unit tests boot
  the same model the benchmarks measure.
* **IRQs are dispatched, not preemptive**: host code calls
  `isr_dispatch()`; on silicon the same handlers would sit in the vector
  table. Volatile/critical-section/ordering code is identical either way.
* **Engine hooks (tests only)**: tests drive completion/error via
  `vlab_test_*` hooks (documented as test-only in `driver_api.h`), which
  step or latch the live engine — never a parallel register table.
  Timeout waits are bounded poll loops; on silicon the bound would be
  a timer.
* **Peripheral streams are model FIFOs**: DMA RAM→uart-tx appends to a TX
  stream (looped back into the RX stream), DMA uart-rx→RAM drains it;
  CPU single-byte loopback semantics are unchanged. FIFO depth equals the
  max transfer; short RX reads zero-pad, so tests pre-fill exact lengths.
* **No silicon timing**: C tests assert logic and sequencing, never cycles.

## Interview map

* `volatile`: completion flags, shared ISR state, HAL temporaries that keep
  status polls as separate loads; ask to explain what breaks without it
  (cached/stale reads, merged polls, reordered RMW).
* Races: main-line `dma_state()` read vs ISR write; submit critical
  section rationale; why ACK precedes CLEAR and what wedges otherwise.
* Bring-up: why order matters, how `platform_init` codes propagate, what the
  recovery leg proves (ERROR latched with code → recover → clean transfer).

## Silicon note (intended mapping, not compiled here)

This tree is host-native simulation: there is no silicon backend file.
On silicon, `hal_read_reg`/`hal_write_reg` would be volatile pointer
dereferences and `hal_irq_disable`/`hal_irq_restore` would mask/unmask
via PRIMASK (or the interrupt controller), keeping the same
read/write discipline and critical-section structure the host code uses.

## Future work (not started)

* ARM cross-compile preset (`arm-none-eabi-gcc -ffreestanding`) proving
  the drivers build freestanding — no ARM toolchain on this machine yet,
  so no half-added target. RTOS/Linux ports are explicitly deferred (see
  README); the scheduler and platform-driver studies they would need live
  in git history, not in this tree.
