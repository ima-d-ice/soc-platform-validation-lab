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
C firmware drivers + HAL (boot, UART, timer, DMA, INTC, ISR)
    ↓  hal/host.c ↔ host_bridge (system tests) · mmio.c shim (unit tests)
Virtual SoC model in C (soc_c/): CPU / Memory / INTC / Timer / UART / DMA / PERF
    ↓
Deterministic tick clock: every step() advances peripherals underneath software
```

The register map is frozen (`docs/soc-spec.md`,
`firmware/include/soc_regs.h` — do not hand-edit). Time is integer model
ticks. The C model (`soc_c/`) is the single source of truth; the Python
model and harness were removed in the pure-C migration.

## Repository layout

```text
soc_c/include|src/   behavioral SoC model (cpu, memory, bus errors,
                     uart, timer, intc, dma, perf, top-level soc, faults,
                     host_bridge for firmware linkage)
soc_c/tests/         CTest suites: boot, bus errors, DMA, DMA burst,
                     INTC/priority, timer+UART, faults, regions,
                     firmware_link (drivers on the live model)
soc_c/bench/         measurement tools: boot_time, cpu_vs_dma (CSV out)
firmware/hal/        HAL: generic access + RMW + critical sections;
                     backends host.c (sim) / silicon.c (volatile+PRIMASK)
firmware/drivers/    UART / timer / DMA / INTC drivers (+ mmio.c host shim
                     for pure-logic unit tests)
firmware/isr|boot|platforms|apps|tests/  dispatch, boot, VLAB config, demos
docs/                spec, architecture, studies, limitations
configs/             frozen spec data (regs.yaml, base.yaml, fast_mem.yaml)
results/             gitignored measurement output (see results/.gitkeep)
```

## Build and test (no Python, no dependencies beyond CMake + C11)

```bash
cmake -S soc_c -B soc_c/build && cmake --build soc_c/build
ctest --test-dir soc_c/build --output-on-failure   # 9 suites: model + firmware link

cmake -S firmware -B firmware/build && cmake --build firmware/build
ctest --test-dir firmware/build --output-on-failure  # 9 suites: drivers/HAL/ISR/boot
```

## Benchmarks

```bash
./soc_c/build/soc_c_boot_time
# {"boot_ticks": 5, "cpu_frequency_mhz": 100, "boot_ns": 50, ...}

./soc_c/build/soc_c_cpu_vs_dma   # CSV: size,burst,words,bursts,dma_ticks,cpu_ticks
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

## Interview prep

`docs/interview-prep.md` is a private local note and is gitignored — it
is never committed or pushed.
