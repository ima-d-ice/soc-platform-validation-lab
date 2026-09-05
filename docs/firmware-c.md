# Firmware in C — what is real and what is host behavior

The C side (`firmware/`) is genuine embedded firmware structure compiled
with `-Wall -Wextra -Werror` (C11): a HAL, five drivers, a dispatched ISR
framework, boot sequencing, an event-driven demo app, and CTest unit tests
(`hal_unit`, `drivers_unit`, `isr_unit`, `firmware_smoke`, `isr_demo_fw`).

## What is real C

* **HAL** (`hal/hal.c`, `include/hal.h`): `read_reg`/`write_reg` as
  volatile-qualified accesses, `set/clear/modify_bits` RMW helpers,
  `irq_disable/restore` critical-section structure. All drivers use it;
  nothing touches `vlab_mmio_*` outside HAL/mmio.
* **Driver logic**: validation ordering (BUSY→LEN→ALIGN→ADDR, mirroring the
  `soc_c` model), bit composition, W1C handling, error codes,
  bounded poll loops with timeout returns.
* **ISR discipline**: vector table + registration (`isr/isr.c`), volatile
  ISR/main shared flags, critical sections around submit/recover state
  transitions, ACK-then-clear ordering inside the ISR, bounded dispatch so
  a babbling source cannot livelock the loop.
* **State machines**: DMA lifecycle
  `IDLE→STARTING→ACTIVE→COMPLETE→(recover)→IDLE` /
  `ACTIVE→ERROR→(recover)→IDLE`, and the demo app’s system machine
  `IDLE→STARTING→ACTIVE→COMPLETE→ERROR→RECOVERY`. Illegal transitions are
  rejected (submit requires IDLE; recover acts only from terminal states).
* **Init sequencing** (`apps/isr_demo.c:sys_init`): ordered bring-up with
  failure propagation — later stages never run on an earlier failure.

## What is host behavior (stated, not hidden)

* **Registers, two levels**: pure-logic unit tests use a static-table
  shim (`drivers/mmio.c`), not silicon. It faithfully mirrors reset
  values, W1C, START-self-clear, and fixed INTC priority so driver logic
  is genuinely exercised. System tests (`soc_c_firmware_link`) skip the
  shim: `soc_c/host_bridge` routes HAL traffic into the live ticking
  `soc_c` engine (UART latency, timer countdown, DMA bursts, IRQ
  coalescing), stepped explicitly.
* **IRQs are dispatched, not preemptive**: host code calls
  `isr_dispatch()`; on silicon the same handlers would sit in the vector
  table. Volatile/critical-section/ordering code is identical either way.
* **Engine stand-ins (unit tests only)**: the shim has no ticking engine,
  so unit tests and the demo drive completion/error via `vlab_test_*`
  hooks (documented as test-only in `driver_api.h`). System tests drive
  the real `soc_c` engine instead. Timeout waits are bounded poll loops;
  on silicon the bound would be a timer.
* **No silicon timing**: C tests assert logic and sequencing, never cycles.

## Interview map

* `volatile`: completion flags, shared ISR state, HAL temporaries that keep
  status polls as separate loads; ask to explain what breaks without it
  (cached/stale reads, merged polls, reordered RMW).
* Races: main-line `dma_state()` read vs ISR write; submit critical
  section rationale; why ACK precedes CLEAR and what wedges otherwise.
* Bring-up: why order matters, how `sys_init` codes propagate, what the
  recovery leg proves (ERROR latched with code → recover → clean transfer).

## Future work (not started)

* ARM cross-compile preset (`arm-none-eabi-gcc -ffreestanding`) proving
  the drivers build freestanding — no ARM toolchain on this machine yet,
  so no half-added target. The non-`VLAB_HOST_SIM` HAL path is already
  written for it (volatile pointers, PRIMASK asm).
