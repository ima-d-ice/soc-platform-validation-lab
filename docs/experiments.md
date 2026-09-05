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
