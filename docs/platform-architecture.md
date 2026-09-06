# Platform Architecture — what is general, configured, or VLAB-specific

Every concept in this repository carries exactly one of these labels:

- **GENERAL CONCEPT** — true of embedded/SoC systems broadly; implemented
  as generic mechanisms (tables, capabilities, error codes).
- **PLATFORM CONFIGURATION** — data describing one concrete platform;
  lives in `configs/` or `firmware/platform/`, never in logic.
- **CURRENT VLAB IMPLEMENTATION** — the choices this virtual SoC makes;
  valid here, not universal truths.

## Dependency map

```text
tests/*, bench/*  (harness: builds SoCs, drives scenarios)
        |
firmware/platform/  (PLATFORM CONFIGURATION: memory map, DMA caps,
  DMA-capable peripheral FIFOs, IRQ map, platform_init — the single
  construction site for platform data)
        |
soc_c/*, firmware/hal, firmware/isr
  (GENERAL CONCEPT mechanisms: decode/step/boot, regions, caps-checked
  validation, coalescing dispatch, access primitives, crit sections)
        |
configs/regs.yaml -> firmware/include/soc_regs.h
  (PLATFORM CONFIGURATION, frozen: the register contract both sides share)
```

One root `CMakeLists.txt` builds two libraries: `soc_model` (SoC plus the
platform data file) and `vlab_firmware` (drivers on top of the model).
There is exactly one register path: driver → HAL → host bridge → SoC bus
→ memory/peripheral model. No second shim exists.

Per component:

| Component | Calls into | Represents | Generic | VLAB-specific |
|---|---|---|---|---|
| `bus` `SOC_ERR_BUS` | returned everywhere | bus fault signal + decode | ✅ | — |
| `memory` regions | SoC decode, DMA validation | map-as-data + range math | ✅ helpers | table contents |
| `soc.c` SoC | tests, benches | integration, tick, boot | flow | map/caps/IRQ (VLAB bases) |
| `soc_cpu` | SoC boot | CPU state (CPU ≠ SoC) | ✅ state | ROM/SP layout |
| `dma` + caps + periph FIFOs | SoC step, benches | burst engine, endpoint/role validation | lifecycle, burst math, 2-step clear | caps values, uart-tx/rx FIFO table, IRQ line |
| `intc` | peripherals | coalescing controller | ack/active semantics | lines 0/1/2 + order |
| `firmware/hal/` | all drivers/ISR | access primitives | ✅ interface | host backend into live model |
| `firmware/drivers/dma` | apps, tests | validation + lifecycle + ISR | endpoint/role/direction order, lifecycle, codes | caps/map/periph-FIFOs from platform |
| `firmware/isr` | apps, tests | generic dispatch | ✅ dispatcher | line count + numbers from platform |
| `firmware/platform/` | dma driver, SoC init | VLAB data + bring-up | table pattern | all values |
| `host_bridge` | firmware_link test | firmware-on-model binding | single-instance pattern | — |

## The teaching progression (read the repo in this order)

```text
CPU        soc_c/src/soc_cpu.c   state, reset (CPU is one part of the SoC)
SoC        soc_c/src/soc.c       integration point
Bus        soc_c/src/bus.c       decode: who owns this address?
MMIO       soc_memory + map      regions, permissions, decode
HAL        firmware/hal/         volatile access, RMW, crit sections
Driver     firmware/drivers/     init/start/stop/status/error/recover
ISR        firmware/isr.c        dispatch, volatile sharing, crit sections
DMA        both dma sides        caps, validation split, async completion
Link       host_bridge           drivers on the live model, stepping
Validation tests/               determinism, golden numbers
```

## Additive errata (behavior-preserving extensions, not spec breaks)

- DMA error code 4 (`ERR_UNSUPPORTED` / `VLAB_DMA_ERR_UNSUPPORTED`):
  mapped-but-incapable endpoint, wrong FIFO role, disallowed direction,
  or over-max length. Codes 0–3 keep frozen meanings.
- `isr_configure(n)`: platforms with fewer live lines than the
  controller; ACK side effects still follow the controller contract.
