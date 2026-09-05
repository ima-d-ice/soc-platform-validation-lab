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
benchmarks/    quantitative experiments (boot, cpu-vs-dma, fault injection)
tools/         reggen + plotting + reporting helpers
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

# Phase-5 fault injection (real measurement from model; results gitignored)
python3 benchmarks/fault_injection.py \
  --config configs/base.yaml \
  --faults dma-invalid,dma-timeout,uart-stuck,irq-storm,mmio-invalid \
  --reps 5 \
  --out results/fault_injection.json
python3 tools/plot_faults.py --input results/fault_injection.json

# Phase-6 RTOS scheduling (model ticks; results gitignored)
python3 benchmarks/rtos_scheduling.py \
  --config configs/base.yaml \
  --reps 5 \
  --out results/rtos_scheduling.json
python3 tools/plot_rtos.py --input results/rtos_scheduling.json

# Phase-7 Linux platform (model ticks; userspace driver model; gitignored)
python3 benchmarks/linux_platform.py \
  --config configs/base.yaml \
  --sizes 64,256,1024,4096,16384 \
  --reps 5 \
  --out results/linux_platform.json
python3 tools/plot_linux.py --input results/linux_platform.json
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

Phase-5 fault injection (see `docs/fault-injection.md`, same model):
deterministic fault latches + validation-tick budgets + explicit recovery
state machine. Measured: invalid DMA fails synchronously with zero
corruption (det 2 ticks); stuck DMA/UART caught by budgets (76/20 ticks)
and recovered via abort/unlatch; storms coalesce with strict ACK order
1, 2, 0; all MMIO violations raise BusError with +1 STALLS; mid-activity
resets restore documented reset values and re-init succeeds. All 55
benchmark runs end RECOVERED with byte-identical destinations; no
UNRECOVERABLE instance exists in this matrix (branch unit-tested only).

Phase-6 RTOS (see `docs/rtos.md`; deterministic scheduler modeling
FreeRTOS semantics on the shared SoC tick clock, not the FreeRTOS
kernel): priority swap on identical overload halves mean latency
(107.2 → 57.1 ticks) and un-starves telemetry; processing-load knee
between proc-4 and proc-8 against a 9-tick deadline (100% miss from
proc-8); queue depth trades drops (19→0) against miss rate (0%→87.5%);
periodic wakes exact except overloaded P-10 (jitter 1.43, 100% miss).

Phase-7 Linux platform (see `docs/linux-platform.md`; userspace driver
model, explicitly not a kernel driver): deeper rings raise e2e latency
while absorbing bursts; depth-1 halves throughput (~1.6 vs ~3.2 B/tick);
polling vs notification take identical ticks here and differ only in
handling (STATUS reads vs 1 IRQ + 3 MMIO ops); throughput converges to
~3.2 B/tick; zero data mismatches in all 200 cells. Found and fixed one
genuine model bug: post-START SRC corruption now surfaces as ERR_ADDR
instead of escaping the tick loop.

Deferred: config sweeps.
