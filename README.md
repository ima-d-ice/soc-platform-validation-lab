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

# Phase-4 DMA study (real measurement from model; results gitignored)
python3 benchmarks/cpu_vs_dma.py \
  --config configs/base.yaml \
  --sizes 16,64,256,1024,4096,16384 \
  --bursts 1,2,4,8,16 \
  --completion both \
  --reps 5 \
  --out results/cpu_vs_dma_phase4.json
python3 tools/plot_dma.py --inp results/cpu_vs_dma_phase4.json --outdir results/plots
```

See `docs/soc-spec.md` for the memory map and register contract.
`firmware/include/soc_regs.h` is **generated** by `tools/reggen.py` — do not hand-edit.

## Scope

Implemented and validated: spec + bus/memory/cpu + UART/Timer + complete
deterministic INTC (fixed priority TIMER > DMA > UART, read-to-ack,
coalesced pending, UART RX IRQ) + burst DMA with completion/error IRQ +
C boot/drivers/app + boot/UART/Timer/INTC/DMA validation + boot benchmark.

Phase-4 DMA study (see `docs/dma-optimization.md`, all within the virtual
SoC timing model on `configs/base.yaml`): CPU copy costs 3 ticks/word;
DMA follows `words*1 + (bursts-1)` ticks; burst 1→16 cuts 16KB DMA ticks
from 8191 to 4351; polling vs IRQ completion take identical ticks here and
differ only in handling (IRQ: +2 MEM_ACC, 1 IRQ); DMA already wins on ticks
at the smallest tested size (16B), so no interior crossover was observed;
bus ops avoided grow from -6 at 16B to +3063 at 16KB (derived).

Deferred: fault injection, config sweeps, FreeRTOS/Linux.
