# Experiments

Deterministic, model-tick experiments in this repository. Every number is
produced by running the listed command against the virtual SoC timing model
(`configs/base.yaml` unless stated); result JSON and plots live under
`results/` and are gitignored but reproducible.

## Boot (`benchmarks/boot_time.py`)

```bash
python3 benchmarks/boot_time.py --config configs/base.yaml --runs 3
```

REAL OBSERVATION: Reset → main entry takes 5 model ticks (50 ns at the
informational 100 MHz), deterministic across runs.

## CPU vs DMA data path (`benchmarks/cpu_vs_dma.py`, see `docs/dma-optimization.md`)

```bash
python3 benchmarks/cpu_vs_dma.py \
  --config configs/base.yaml \
  --sizes 16,64,256,1024,4096,16384 \
  --bursts 1,2,4,8,16 \
  --completion both \
  --reps 5 \
  --out results/cpu_vs_dma_phase4.json
python3 tools/plot_dma.py --inp results/cpu_vs_dma_phase4.json --outdir results/plots
```

REAL OBSERVATIONS: CPU copy costs 3 ticks/word (modeled wait); DMA follows
`words*1 + (bursts-1)` ticks; burst 1→16 cuts 16KB DMA ticks 8191→4351;
polling vs IRQ completion take identical ticks here (+2 MEM_ACC and 1 IRQ
for the IRQ path); DMA wins on ticks from the smallest tested size (16B).

## RTOS scheduling (`benchmarks/rtos_scheduling.py`, see `docs/rtos.md`)

```bash
python3 benchmarks/rtos_scheduling.py \
  --config configs/base.yaml \
  --reps 5 \
  --out results/rtos_scheduling.json
python3 tools/plot_rtos.py --input results/rtos_scheduling.json
```

REAL OBSERVATIONS: priority swap on identical overload changes mean
latency 107.2 → 57.1 ticks; load knee between proc-4/proc-8 vs a 9-tick
deadline; queue depth trades 19→0 drops against 0%→87.5% miss rate;
periodic wakes exact except overloaded P-10 (jitter 1.43).

## Linux platform (`benchmarks/linux_platform.py`, see `docs/linux-platform.md`)

```bash
python3 benchmarks/linux_platform.py \
  --config configs/base.yaml \
  --sizes 64,256,1024,4096,16384 \
  --reps 5 \
  --out results/linux_platform.json
python3 tools/plot_linux.py --input results/linux_platform.json
```

REAL OBSERVATIONS: depth-1 halves throughput (~1.6 vs ~3.2 B/tick);
polling vs notification identical ticks, reads-vs-IRQ tradeoff; throughput
converges to ~3.2 B/tick; zero mismatches in all 200 cells.

## Final system matrix (`benchmarks/final_matrix.py`, report `tools/final_report.py`)

```bash
python3 benchmarks/final_matrix.py --config configs/base.yaml \
  --sizes 64,1024,4096,16384 --reps 3 --out results/final_matrix.json
python3 tools/final_report.py --input results/final_matrix.json \
  --out results/final_report.md
python3 tools/final_plots.py --input results/final_matrix.json \
  --outdir results/plots
```

EXP-F1..F8 reuse the phase benchmark definitions by import (no
redefinition): CPU/DMA scaling, burst scaling, polling-vs-IRQ view,
buffering, RTOS priority, Linux behavior, fault detection/recovery, and
seven deterministic stress scenarios (high IRQ rate, DMA pressure, queue
pressure, starvation, comm timeout, invalid access, repeated reset).
Bottlenecks are derived dominant shares with the combinational-MMIO
caveat stated alongside.

## Fault injection (`benchmarks/fault_injection.py`, see `docs/fault-injection.md`)

```bash
python3 benchmarks/fault_injection.py \
  --config configs/base.yaml \
  --faults dma-invalid,dma-timeout,uart-stuck,irq-storm,mmio-invalid \
  --reps 5 \
  --out results/fault_injection.json
python3 tools/plot_faults.py --input results/fault_injection.json
```

REAL OBSERVATIONS: invalid DMA fails synchronously with zero corruption;
stuck faults freeze exactly one counter and are caught by tick budgets
(DMA 76, UART 20 ticks); storms coalesce with strict ACK order 1, 2, 0;
all 55 runs end RECOVERED with byte-identical destinations.

## honesty rules (all experiments)

* **measured**: ticks/counters/registers read from the model.
* **derived**: arithmetic on measured values (throughput, speedup, latencies).
* **modeled**: wait/timing/budget assumptions stated in each doc.
* Wording is always “within the virtual SoC timing model” — never ARM/MCU/
  silicon performance.
