# SoC Platform & Pre-Silicon Validation Lab (pure C)

> A host-native behavioral virtual SoC in C11 for firmware and driver
> development, validation, and performance analysis before hardware exists.

## What problem it solves

SoC software (firmware, drivers, platform layers) is usually written
against hardware that does not exist yet. This project builds a small,
fully deterministic virtual SoC — CPU, memory map, MMIO peripherals,
interrupt controller, timers, UART, DMA, performance counters — plus the
C firmware, drivers, and CTest harnesses needed to develop and
characterize system software pre-silicon-style: boot, data movement,
interrupts, faults, and recovery, all measured in model ticks.

## Architecture

```text
Application / tests (CTest executables)
    ↓
C firmware drivers + HAL (UART, timer, DMA, INTC, ISR, platform_init)
    ↓  hal/host.c → host bridge → SoC bus (ONE live model for everything)
Virtual SoC model in C (soc_c/): CPU / Bus / Memory / UART / Timer / INTC / DMA / PERF
    ↓
Deterministic tick clock: every step() advances peripherals underneath software
```

The register map is frozen (`docs/soc-spec.md`,
`firmware/include/soc_regs.h` — do not hand-edit). Time is integer model
ticks. Map/caps vocabulary (`memory_region`, `dma_caps`, endpoint
helpers) lives once in `firmware/include/` and is shared by the model,
the drivers, and the tests.

## Repository layout

```text
soc_c/             behavioral SoC model: soc.h (one header) + cpu, memory,
                   bus, uart, timer, intc, dma, perf, top-level soc,
                   host_bridge (firmware linkage)
soc_c/tests/       boot, bus_errors (+map), endpoints (DMA matrix+burst),
                   intc, timer_uart, faults, firmware_link (drivers live)
soc_c/bench/       boot_time, cpu_vs_dma (CSV/JSON metrics to stdout)
firmware/include/  hal.h, driver_api.h, mem_regions.h, dma_caps.h, isr.h,
                   soc_regs.h (frozen register map)
firmware/hal/      hal.c (generic RMW) + host.c (live-model backend)
firmware/drivers/  uart.c, timer.c, intc.c, dma.c (endpoint-general DMA)
firmware/isr.c     vector table + bounded dispatch
firmware/platform/ VLAB config: map, caps, DMA FIFOs, IRQ map, platform_init
firmware/apps/     main.c (bring-up demo + metrics printout)
firmware/tests/    unit/ (hal, regions, caps, drivers),
                   integration/ (isr, dma), fault/ (dma_faults)
docs/              spec, architecture, studies, limitations
configs/           frozen spec data (regs.yaml, base.yaml)
results/           gitignored measurement output
```

One root build owns everything (see below). RTOS/Linux ports are
explicitly future extensions, not part of this tree.

## Build and test (no dependencies beyond CMake + a C11 compiler)

```bash
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure   # 15 suites: model + firmware + smoke
```

## Benchmarks

```bash
./build/bench_boot
# {"boot_ticks": 5, "cpu_frequency_mhz": 100, "boot_ns": 50, ...}

./build/bench_dma   # CSV: size,burst,words,bursts,dma_ticks,cpu_ticks
```

Every run is deterministic: same scenario → identical ticks and
byte-identical destinations. See `docs/experiments.md` for methodology
and `docs/dma-optimization.md` / `docs/fault-injection.md` for studies.

## Key measured findings (all within the configured virtual SoC model)

* **Boot:** reset → main in 5 ticks (50 ns at informational 100 MHz).
* **Data movement:** CPU copy 3 ticks/word; DMA `words*1 + (bursts-1)`;
  burst 1→16 cuts 16KB DMA 8191→4351 ticks.
* **Interrupts:** fixed priority TIMER > DMA > UART; pending coalesces,
  ACK order strict; spurious/double ACK returns `0xFFFFFFFF`.
* **Faults:** invalid DMA fails synchronously with zero corruption;
  stuck-busy latches freeze one counter and are caught by tick budgets;
  two-step clear (DMA.IRQ_CLEAR then INTC.CLEAR) on every recovery path.

## Limitations

`docs/limitations.md`: model-only ticks, combinational MMIO, modeled
waits/budgets, no contention/caches/masters, single DMA channel, bounded
fault classes, 16KB transfer cap. Nothing here is ARM/MCU/silicon data.
