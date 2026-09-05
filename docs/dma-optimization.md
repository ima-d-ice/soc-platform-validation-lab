# DMA Data-Path Optimization Study (Phase 4)

Controlled experiments **within the virtual SoC timing model** (`configs/base.yaml`).
Nothing here describes ARM hardware, MCU DMA timing, silicon, bus bandwidth,
or real interrupt latency. All numbers below were measured by running
`benchmarks/cpu_vs_dma.py` against the behavioral model; plots in
`results/plots/` are rendered from `results/cpu_vs_dma_phase4.json`
(both gitignored, reproducible via the command in Methodology).

## Experiment questions

1. How does DMA performance change with burst size? (Experiment A)
2. How does DMA performance scale with transfer size? (Experiment B)
3. What is the difference between status-polling and IRQ completion? (Experiment C)
4. At what transfer size does DMA become preferable in this model? (Crossover)
5. How much CPU work is avoided by using DMA? (Experiment D)

## Model assumptions

* Tick-stepped behavioral model; `cpu_frequency_mhz: 100` converts ticks to ns
  for reporting only.
* CPU copy: word loop of `soc.read` + `soc.write` + `step(1 + ram_latency_ticks)`.
  With `ram_latency_ticks: 2` this is **3 ticks/word** — a modeling choice, not
  a hardware measurement.
* DMA timing formula (preserved from Step 2, documented — not replaced):
  `words = LEN/4; bursts = ceil(words/burst);`
  `ticks = words * dma_latency_per_word_ticks + (bursts - 1) * 1`.
  Burst size is config-only (`dma_burst`); there is no BURST register.
* MMIO setup/ACK bus accesses are combinational in this model (zero ticks,
  counted in MEM_ACC, not in tick totals).
* SRAM is 64KB; regions are SRC @+0x0000, CPU_DST @+0x4000, DMA_DST @+0x8000.
  Single transfers are therefore capped at 16KB; 64KB was requested but does
  not fit and was not run.

## What is measured / derived / modeled

| Class | Metrics |
|---|---|
| **Measured** (model counters) | `total_ticks`, `dma_transfer_ticks`, `dma_bytes`, `mem_accesses` (MEM_ACC delta), `irq_count`, `stalls`, `cpu_ticks`, poll `status_reads`, `destination_match` (asserted byte compare) |
| **Derived** (arithmetic on measured) | throughput (B/tick), speedup, crossover point, `cpu_work_avoided_bus_ops` |
| **Modeled** (assumption) | CPU 3 ticks/word wait; burst +1 overhead per extra burst |

## Benchmark methodology

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

Fresh `SoC` + `boot()` per measurement; 300 cells (6 sizes x 5 bursts x
2 modes x 5 reps). Reps are bit-identical (`deterministic_across_reps: true`).

## REAL OBSERVATIONS (base config, rep 0)

Burst = 4, IRQ completion vs CPU copy:

| bytes | cpu_ticks | dma_ticks | speedup | cpu B/tick | dma B/tick | cpu mem | dma mem | irq |
|---|---|---|---|---|---|---|---|---|
| 16 | 12 | 4 | 3.00x | 1.333 | 4.000 | 8 | 14 | 0/1 |
| 64 | 48 | 19 | 2.53x | 1.333 | 3.368 | 32 | 29 | 0/1 |
| 256 | 192 | 79 | 2.43x | 1.333 | 3.241 | 128 | 89 | 0/1 |
| 1024 | 768 | 319 | 2.41x | 1.333 | 3.210 | 512 | 329 | 0/1 |
| 4096 | 3072 | 1279 | 2.40x | 1.333 | 3.203 | 2048 | 1289 | 0/1 |
| 16384 | 12288 | 5119 | 2.40x | 1.333 | 3.201 | 8192 | 5129 | 0/1 |

Burst sweep (DMA total ticks, IRQ mode):

| bytes | b=1 | b=2 | b=4 | b=8 | b=16 |
|---|---|---|---|---|---|
| 16 | 7 | 5 | 4 | 4 | 4 |
| 64 | 31 | 23 | 19 | 17 | 16 |
| 256 | 127 | 95 | 79 | 71 | 67 |
| 1024 | 511 | 383 | 319 | 287 | 271 |
| 4096 | 2047 | 1535 | 1279 | 1151 | 1087 |
| 16384 | 8191 | 6143 | 5119 | 4607 | 4351 |

Polling vs IRQ (burst=4): **identical total/transfer ticks at every size**
(e.g. 16B: 4/4; 16KB: 5119/5119). The difference is handling cost, not time:
polling does N+1 STATUS reads with `irq_count=0`; IRQ does 3 post-transfer
reads + ACK/CLEAR with `irq_count=1` and exactly **+2 MEM_ACC** vs polling at
every size (e.g. 12 vs 14 at 16B; 5127 vs 5129 at 16KB). Stalls were 0 in all
cells. `destination_match` was true in all 300 runs.

## MODEL BEHAVIOR (why the curves look this way)

* Larger bursts strictly reduce ticks here because the only burst term is the
  +(bursts-1) overhead; per-word cost is burst-independent. Gains saturate
  once a transfer fits in one burst (e.g. 16B identical for burst >= 4).
* Speedup converges with size toward the per-word ratio 3:1 minus overhead
  (~2.40x at burst=4, ~1.50x at burst=1, ~2.83x at burst=16).
* Polling/IRQ tick equality is a property of this model (both poll STATUS each
  tick; ACK path is combinational). It must not be read as “IRQs are free”.

## DERIVED METRICS

* **Crossover**: DMA `total_ticks < cpu_ticks` already at 16B for every
  (burst, mode) cell, so the smallest tested size is the crossover. No claim
  is made below 16B (not measured).
* **CPU work avoided** (`cpu_mem - dma_mem` bus ops, IRQ mode, burst=4):
  16B: **-6** (DMA costs more bus ops than the copy it replaces);
  64B: +3; 256B: +39; 1KB: +183; 4KB: +759; 16KB: +3063.
  Labeled derived: it is a subtraction of two counters, not a hardware probe.

## Limitations

* No bus contention, caches, arbitration with other masters, or real ISR
  entry cost; MMIO is combinational; single channel; no chained transfers.
* 64KB single transfers exceed the 64KB SRAM and were excluded by a runtime
  fit check rather than worked around.
* Results are valid only for the stated config; change `ram_latency_ticks`,
  `dma_latency_per_word_ticks`, or `dma_burst` and all numbers move.
