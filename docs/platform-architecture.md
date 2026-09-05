# Platform Architecture — what is general, configured, or VLAB-specific

Every concept in this repository carries exactly one of these labels:

- **GENERAL CONCEPT** — true of embedded/SoC systems broadly; implemented
  as generic mechanisms (tables, capabilities, error codes).
- **PLATFORM CONFIGURATION** — data describing one concrete platform;
  lives in `configs/`, generated headers, or `firmware/platforms/vlab/`,
  never in logic.
- **CURRENT VLAB IMPLEMENTATION** — the choices this virtual SoC makes;
  valid here, not universal truths.

## Dependency map

```text
soc_c/tests/*, soc_c/bench/*  (harness: builds SoCs, drives scenarios)
        |
firmware/platforms/vlab/  (PLATFORM CONFIGURATION: memory map, DMA caps,
  IRQ map — the single construction site for firmware data)
        |
soc_c/src/*, firmware/hal, firmware/isr
  (GENERAL CONCEPT mechanisms: decode/step/boot, regions, caps-checked
  validation, coalescing dispatch, access primitives, crit sections)
        |
configs/regs.yaml -> firmware/include/soc_regs.h
  (PLATFORM CONFIGURATION, frozen: the register contract both sides share;
  the former tools/reggen.py generator was removed in the pure-C migration)
```

Per component:

| Component | Calls into | Represents | Generic | VLAB-specific |
|---|---|---|---|---|
| `soc_bus.h` `SOC_ERR_BUS` | returned everywhere | bus fault signal | ✅ | — |
| `soc_memory` regions | SoC decode, DMA validation | map-as-data + range math | ✅ helpers | table contents |
| `soc.c` SoC | tests, benches | integration, tick, boot | flow | map/caps/IRQ (VLAB bases) |
| `soc_dma` + caps | SoC step, benches | burst engine | lifecycle, burst math, 2-step clear | caps values, IRQ line |
| `soc_intc` | peripherals | coalescing controller | ack/active semantics | lines 0/1/2 + order |
| `soc_faults` | fault tests | latch injector + recovery machine | ✅ | budgets live in callers |
| `firmware/hal/` | all drivers/ISR | access primitives + backends | ✅ interface | backend choice (host vs silicon) |
| `firmware/drivers/dma/` | apps, tests | validation + lifecycle + ISR | order, lifecycle, codes | caps/map from `platforms/vlab/` |
| `firmware/isr/` | apps, tests | generic dispatch | ✅ dispatcher | line count + numbers from platform |
| `firmware/platforms/vlab/` | dma driver | VLAB data | table pattern | all values |
| `soc_c/host_bridge` | firmware_link test | firmware-on-model binding | shim pattern | VLAB addresses |

## The teaching progression (read the repo in this order)

```text
CPU        soc_c/src/soc_cpu.c   state, reset
SoC        soc_c/src/soc.c       integration point
Bus        soc_c/include/soc_bus.h  faults as values
MMIO       soc_memory + map      regions, permissions, decode
HAL        firmware/hal/         volatile access, RMW, backends
Driver     firmware/drivers/     init/configure/start/stop/status/error/recover
ISR        firmware/isr/         dispatch, volatile sharing, crit sections
DMA        both dma sides        caps, validation split, async completion
Link       soc_c/host_bridge     drivers on the live model, stepping
Validation soc_c/tests/ + firmware/tests/  determinism, golden numbers
```

## Additive errata (behavior-preserving extensions, not spec breaks)

- DMA error code 4 (`ERR_UNSUPPORTED` / `VLAB_DMA_ERR_UNSUPPORTED`):
  mapped-but-unsupported endpoint, direction, or over-max length.
  Codes 0–3 keep frozen meanings.
- `isr_configure(n)`: platforms with fewer live lines than the
  controller; ACK side effects still follow the controller contract.
