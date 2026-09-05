# vlab-soc Specification v0.3 (INTC complete; DMA burst)

This is the imaginary silicon's contract. The Python model (`soc/`) and the
C firmware (`firmware/`) MUST both conform to it. `firmware/include/soc_regs.h`
is generated from `configs/regs.yaml` by `tools/reggen.py` and matches this
document.

Status: INTC complete; DMA burst + completion/error IRQ. Chained mode,
fault-injection behaviour beyond bus errors, and config-sweep characterisation
are explicitly **deferred**.

Changelog v0.2 -> v0.3: DMA burst timing `ticks = words*latency_per_word +
(bursts-1)` with `bursts = ceil(words/dma_burst)` (config-only, no new
registers, no address changes); completion + error IRQs on line 2 with
two-step clear (DMA.IRQ_CLEAR then INTC.CLEAR).

Changelog v0.1 -> v0.2: UART raises INTC line 0 on RX_VALID completion
(delivery gated solely by INTC.ENABLE; no new registers, no address changes);
INTC semantics completed (coalesced pending, read-to-ack, spurious/double-ack,
invalid-CLEAR ignore, non-preemptive queueing).

## 1. Memory map

| Base         | Size  | Name  | Access    | Notes                          |
|--------------|-------|-------|-----------|--------------------------------|
| `0x00000000` | 16 KiB| ROM   | r-x       | Boot image, read-only at run   |
| `0x10000000` | 64 KiB| SRAM  | rw-       | DMA-visible, word-aligned MVP  |
| `0x20000000` | 4 KiB | UART  | rw (per-reg) | Loopback model              |
| `0x20001000` | 4 KiB | TIMER | rw (per-reg) | Countdown, one-shot/periodic|
| `0x20002000` | 4 KiB | DMA   | rw (per-reg) | Single transfer only (MVP)  |
| `0x20003000` | 4 KiB | INTC  | rw (per-reg) | 3 lines, fixed priority     |
| `0x20004000` | 4 KiB | PERF  | rw (per-reg) | Counters                    |

All MMIO registers are 32-bit little-endian, word-aligned. See
`configs/regs.yaml` for exact offsets, access (`RW/RO/WO`), and reset values.

## 2. Reset values

* All `RW` control registers reset to `0x00000000` (disabled) except where noted.
* `UART_STATUS` resets to `0x00000002` (`TX_EMPTY=1`).
* `INTC_ACK` reads `0xFFFFFFFF` (`VLAB_IRQ_NONE`) when nothing is pending.
* `PERF_*` counters reset to `0`.

## 3. Access permissions and bus errors

The bus (`soc/bus.py`) raises `BusError` (and counts a stall) on:

1. Address outside any mapped region.
2. Write to `RO`, read from `WO`.
3. Unaligned 32-bit access (`addr % 4 != 0`).
4. Byte/half-word access (MVP supports word accesses only on MMIO; SRAM
   supports byte accesses via DMA model only — CPU uses words).
5. ROM write at run time.

C drivers MUST check return codes; validation MUST assert invalid-register
rejection (`test_bus_errors`).

## 4. Interrupt lines (fixed)

| Line | Source | MVP priority |
|------|--------|--------------|
| 0    | UART   | lowest (2)   |
| 1    | TIMER  | highest (0)  |
| 2    | DMA    | middle (1)   |

Priority order: `TIMER > DMA > UART`. The controller is non-preemptive and
queued: `INTC_ACK` returns the highest pending+enabled line, moves it
`PENDING -> ACTIVE`, and `INTC_CLEAR` (write irq number) clears `ACTIVE`.
`PENDING` is read-only. `ENABLE` gates `ACK` only (pending still records while
disabled). Raises coalesce: N raises before an ACK yield one pending bit and
one ACK. Spurious ACK returns `0xFFFFFFFF` and counts nothing; double-ACK of
the same event returns `0xFFFFFFFF`; `CLEAR` of an out-of-range number is
ignored and clearing an inactive line is a no-op.

## 5. Registers

### 5.1 UART (`0x20000000`)

| Offset | Name      | Access | Reset | Meaning |
|--------|-----------|--------|-------|---------|
| 0x00 | TXDATA    | WO | 0 | Write `bits[7:0]` to transmit (loopback to RX). Requires `CTRL.ENABLE=1`, else bus-legal no-op returning `UART_ERR_DISABLED`. |
| 0x04 | RXDATA    | RO | 0 | Last looped-back byte, valid when `STATUS.RX_VALID=1`. Read does **not** clear; reading `RXDATA` clears `RX_VALID` (MVP). |
| 0x08 | STATUS    | RO | 0x2 | `bit0 TX_BUSY`, `bit1 TX_EMPTY`, `bit2 RX_VALID`. `TX_BUSY` asserted for `uart_latency_ticks` after TX. |
| 0x0C | CTRL      | RW | 0 | `bit0 ENABLE`. |
| 0x10 | BAUDDIV   | RW | 0 | Informational only in MVP. |

UART IRQ (line 0): raised on RX_VALID completion (loopback byte ready after
`uart_latency_ticks`). Delivery is gated solely by `INTC.ENABLE` bit 0;
polling via `STATUS` remains available.

### 5.2 TIMER (`0x20001000`)

| Offset | Name | Access | Reset | Meaning |
|--------|------|--------|-------|---------|
| 0x00 | CTRL | RW | 0 | `bit0 ENABLE`, `bit1 PERIODIC`, `bit2 IRQ_ENABLE` |
| 0x04 | LOAD | RW | 0 | Reload value in model ticks |
| 0x08 | VALUE | RO | 0 | Current countdown |
| 0x0C | IRQ_STATUS | RW | 0 | `bit0 FIRED` (W1C) |
| 0x10 | IRQ_CLEAR | WO | 0 | Write 1 to clear `FIRED` |

Behaviour: when `ENABLE=1`, `VALUE` decrements once per `soc.step()` tick.
When it reaches 0: set `FIRED=1`, raise INTC line 1 if `IRQ_ENABLE=1`;
if `PERIODIC=1` reload `VALUE=LOAD`, else `ENABLE` auto-clears (one-shot).
Software clears via `IRQ_STATUS` W1C or `IRQ_CLEAR`.

### 5.3 DMA (`0x20002000`) — burst transfer

| Offset | Name | Access | Reset | Meaning |
|--------|------|--------|-------|---------|
| 0x00 | SRC | RW | 0 | Source byte address |
| 0x04 | DST | RW | 0 | Destination byte address |
| 0x08 | LEN | RW | 0 | Length in bytes |
| 0x0C | CTRL | RW | 0 | `bit0 START`, `bit1 IRQ_ENABLE` |
| 0x10 | STATUS | RO | 0 | `bit0 BUSY`, `bit1 DONE`, `bit2 ERROR` |
| 0x14 | IRQ_CLEAR | WO | 0 | Write 1 clears DONE/ERROR flags (does NOT clear INTC pending) |
| 0x18 | ERR_CODE | RO | 0 | `0 none, 1 invalid addr, 2 misaligned, 3 bad length` |

Contract: software programs `SRC/DST/LEN`, writes `START=1` (`CTRL` auto-clears
`START`, sets `BUSY`, clears `DONE/ERROR`). Burst size comes from platform
config `dma_burst` (words per burst; no BURST register). Transfer completes over
`words * dma_latency_per_word_ticks + (bursts - 1)` ticks where
`words = LEN/4`, `bursts = ceil(words/dma_burst)` (see `configs/base.yaml`),
then `BUSY=0`, `DONE=1` (or synchronous `ERROR=1` + code on validation
failure with no `BUSY` phase), `DMA_BYTES += LEN` on success, INTC line 2
raised on DONE *and* on ERROR iff `IRQ_ENABLE` was set at `START`.
Validation: `SRC/DST` in SRAM, word-aligned, `LEN>0`, multiple of 4;
overlap uses memmove semantics. Clearing is two-step: `DMA.IRQ_CLEAR` clears
DMA flags, then `INTC.CLEAR(2)` clears the pending bit. Chained mode deferred.

### 5.4 INTC (`0x20003000`)

| Offset | Name | Access | Reset | Meaning |
|--------|------|--------|-------|---------|
| 0x00 | ENABLE | RW | 0 | `bit[n]` enables line `n` |
| 0x04 | PENDING | RO | 0 | `bit[n]` set by peripheral |
| 0x08 | ACK | RO | — | Read acks highest pending+enabled line (number or `0xFFFFFFFF`); clears its `PENDING`, sets `ACTIVE` |
| 0x0C | CLEAR | WO | 0 | Write irq number `0..2` to clear `ACTIVE` |
| 0x10 | ACTIVE | RO | 0 | `bit[n]` acked, not yet cleared |

No priority registers (fixed order above). Spurious `ACK` returns
`0xFFFFFFFF` and counts nothing; double-ACK returns `0xFFFFFFFF`;
out-of-range `CLEAR` is ignored.

### 5.5 PERF (`0x20004000`)

| Offset | Name | Access | Reset |
|--------|------|--------|-------|
| 0x00 | CYCLES | RW | 0 |
| 0x04 | MEM_ACC | RW | 0 |
| 0x08 | DMA_BYTES | RW | 0 |
| 0x0C | IRQ_COUNT | RW | 0 |
| 0x10 | STALLS | RW | 0 |
| 0x14 | CTRL | RW | 0 (`bit0 ENABLE`, `bit1 RESET=write-1-to-clear-all`) |

`CYCLES` increments every `soc.step()` when enabled. `MEM_ACC` counts every
bus transaction. `IRQ_COUNT` counts `ACK`s returning a valid line. `STALLS`
counts bus-error + busy-poll ticks. All are real model measurements —
never synthesised.

## 6. Boot flow

```text
Reset -> ROM -> startup (stack, .data copy, .bss zero) -> main()
```

* `Reset` zeroes CPU state, sets PC to ROM base, enables PERF if configured.
* Startup is modelled by `soc.boot(rom_image)`: loads image words into ROM,
  zeroes SRAM `.bss` region, sets SP to SRAM top, jumps to `main` marker.
* C `firmware/boot/boot.c:boot_init()` mirrors this: disables IRQs, inits
  `.data/.bss` (host-native simulation of the copy/zero), inits PERF,UART.
* Boot time = ticks from `Reset` to `main` entry; measured by
  `benchmarks/boot_time.py`, not estimated.

## 7. Clocks and determinism

* The model steps in integer **ticks**. `cpu_frequency_mhz` converts
  ticks->ns only for reporting (`ns = ticks * 1000 / MHz`).
* `configs/base.yaml` is the golden config for MVP tests. Other configs are
  for future sweeps and MUST NOT change MVP expected behaviour except via
  explicit tick-difference assertions.

## 8. Error conditions (MVP)

| Condition | Detection | Reporting |
|-----------|-----------|-----------|
| Invalid MMIO address | bus | `BusError` |
| RO write / WO read | bus | `BusError` |
| Unaligned MMIO | bus | `BusError` |
| ROM write | bus | `BusError` |
| UART TX while disabled | driver | `UART_ERR_DISABLED` |
| TIMER LOAD=0 + ENABLE | peripheral | No fire (stays at 0, no IRQ) |
| DMA bad address/align/len | DMA | `STATUS.ERROR=1` + `ERR_CODE` |
| DMA START while BUSY | DMA | Ignored, `STALLS+=1` |

Watchdog, memory corruption, interrupt-storm, and task-starvation faults are
**deferred** to Phase 10.
