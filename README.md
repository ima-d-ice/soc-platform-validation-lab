# SoC Platform & Pre-Silicon Validation Lab

> A virtual SoC platform used to develop firmware/drivers and validate boot,
> memory-mapped peripherals, interrupts, DMA, power/performance behaviour and
> system software before hardware exists.

This is a **mini pre-silicon development platform** for platform-software /
firmware / validation / performance work — no Verilog/FPGA required.

```
                Application
                     │
                     ▼
             ┌───────────────┐
             │ RTOS / Linux  │  (roadmap)
             └───────┬───────┘
                     │
                Drivers/API (firmware/drivers, C)
                     │
            ┌────────▼─────────┐
            │   SoC Platform   │  (soc/, Python)
            │ CPU / Memory /   │
            │ INTC / Timer /   │
            │ UART / DMA / PERF│
            └────────┬─────────┘
                     │
                Virtual HW
```

Host (Python) controls the experiment. Firmware (C) behaves as if running on the SoC.

## Layout

```text
soc/           Python virtual SoC (bus, memory, cpu, intc, timer, uart, dma, perf)
firmware/      C firmware (boot, drivers, apps) built host-native via CMake
validation/    pytest harness (boot, dma, interrupts, faults, stress)
benchmarks/    quantitative experiments (boot time, cpu vs dma later)
tools/         reggen + reporting helpers
configs/       platform configurations (yaml)
docs/          SoC specification (contract)
results/       generated artefacts (gitignored)
```

## Quickstart (MVP)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build C firmware (host-native, against emulated MMIO)
cmake -S firmware -B firmware/build
cmake --build firmware/build

# Run validation
python3 -m pytest validation/ -q

# Boot-time benchmark (real measurement from model)
python3 benchmarks/boot_time.py --config configs/base.yaml
```

See `docs/soc-spec.md` for the memory map and register contract.
`firmware/include/soc_regs.h` is **generated** by `tools/reggen.py` — do not hand-edit.

## Scope

MVP (§1–§5): spec + bus/memory/cpu + UART/Timer + INTC/PERF stubs +
single-transfer DMA stub + C boot/drivers/app + boot/UART/Timer validation.

Deferred (placeholders only): priority/nesting, burst/chained DMA, fault
injection, config sweeps, FreeRTOS/Linux.
