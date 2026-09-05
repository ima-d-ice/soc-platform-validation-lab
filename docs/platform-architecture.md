# Platform Architecture — what is general, configured, or VLAB-specific

Every concept in this repository carries exactly one of these labels:

- **GENERAL CONCEPT** — true of embedded/SoC systems broadly; implemented
  as generic mechanisms (tables, capabilities, raisable errors).
- **PLATFORM CONFIGURATION** — data describing one concrete platform;
  lives in `platforms/`, `configs/`, or generated headers, never in logic.
- **CURRENT VLAB IMPLEMENTATION** — the choices this virtual SoC makes;
  valid here, not universal truths.

## Dependency map

```text
validation/*, benchmarks/*  (harness: builds platforms, drives scenarios)
        |
platforms/vlab.py, firmware/platforms/vlab/  (PLATFORM CONFIGURATION:
  memory map, DMA caps, IRQ map — the single construction site per side)
        |
soc/{cpu,memory,bus}/, soc/peripherals/*, firmware/hal, firmware/isr
  (GENERAL CONCEPT mechanisms: decode/step/boot, regions, caps-checked
  validation, coalescing dispatch, access primitives, crit sections)
        |
configs/regs.yaml -> tools/reggen.py -> firmware/include/soc_regs.h
  (PLATFORM CONFIGURATION: the frozen register contract both sides share)
```

Per component:

| Component | Calls into | Represents | Generic | VLAB-specific |
|---|---|---|---|---|
| `soc/bus.py` BusError | raised everywhere | bus fault signal | ✅ | — |
| `soc/memory/` regions | SoC decode, DMA validation | map-as-data + range math | ✅ helpers | table contents |
| `soc/soc.py` SoC | tests, benches | integration, tick, boot | flow | map/caps/IRQ from `platforms/vlab.py` |
| `soc/peripherals/dma/` + `caps.py` | SoC step, benches | burst engine | lifecycle, burst math, 2-step clear | caps values, IRQ line |
| `soc/peripherals/intc/` | peripherals | coalescing controller | ack/active semantics | lines 0/1/2 + order |
| `soc/faults.py` | fault tests/bench | latch injector + recovery machine | ✅ | budgets live in callers |
| `firmware/hal/` | all drivers/ISR | access primitives + backends | ✅ interface | backend choice (host vs silicon) |
| `firmware/drivers/dma/` | apps, tests | validation + lifecycle + ISR | order, lifecycle, codes | caps/map from `platforms/vlab/` |
| `firmware/isr/` | apps, tests | generic dispatch | ✅ dispatcher | line count + numbers from platform |
| `firmware/platforms/vlab/` | dma driver | VLAB data | table pattern | all values |
| `linux/`, `rtos/` | benches | streaming/scheduling models | ring, descriptor, priority discipline | SRAM layout, tick costs |

## The teaching progression (read the repo in this order)

```text
CPU        soc/cpu/            state, reset
SoC        soc/soc.py          integration point
Bus        soc/bus/            faults as values
MMIO       soc/memory/ + map   regions, permissions, decode
HAL        firmware/hal/       volatile access, RMW, backends
Driver     firmware/drivers/   init/configure/start/stop/status/error/recover
ISR        firmware/isr/       dispatch, volatile sharing, crit sections
DMA        both dma/           caps, validation split, async completion
RTOS       rtos/               scheduling semantics on the model clock
Platform   linux/              app->driver->MMIO layering, buffers
Validation validation/ + benches  determinism, provenance, golden numbers
```

## Additive errata (behavior-preserving extensions, not spec breaks)

- DMA error code 4 (`ERR_UNSUPPORTED` / `VLAB_DMA_ERR_UNSUPPORTED`):
  mapped-but-unsupported endpoint, direction, or over-max length.
  Codes 0–3 keep frozen meanings; previously-tested cases produce
  identical codes (verified by golden benchmark diffs).
- `isr_configure(n)`: platforms with fewer live lines than the
  controller; ACK side effects still follow the controller contract.
