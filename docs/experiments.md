# Experiments

Deterministic, model-tick experiments in this repository. Every number is
produced by running the listed C binary against the virtual SoC timing
model (default config mirrors `configs/base.yaml`); result output is
reproducible and gitignored (see `results/.gitkeep`).

Prior Python-era studies (RTOS scheduling, Linux platform, final matrix,
plot scripts) were removed in the pure-C migration; their findings remain
in git history. What follows is what the current tree measures.

## Boot (`soc_c_boot_time`)

```bash
cmake -S soc_c -B soc_c/build && cmake --build soc_c/build
./soc_c/build/soc_c_boot_time
```

REAL OBSERVATION: Reset → main entry takes 5 model ticks (50 ns at the
informational 100 MHz), deterministic across runs. Gated by the
`soc_c_boot` CTest.

## CPU vs DMA data path (`soc_c_cpu_vs_dma`, see `docs/dma-optimization.md`)

```bash
./soc_c/build/soc_c_cpu_vs_dma   # CSV: size,burst,words,bursts,dma_ticks,cpu_ticks
```

REAL OBSERVATIONS: CPU copy costs 3 ticks/word (modeled wait); DMA follows
`words*1 + (bursts-1)` ticks; burst 1→16 cuts 16KB DMA ticks 8191→4351;
every cell byte-compares source vs destination (mismatch aborts non-zero).

## Fault injection (`soc_c_faults` CTest, see `docs/fault-injection.md`)

```bash
ctest --test-dir soc_c/build -R soc_c_faults --output-on-failure
```

REAL OBSERVATIONS: invalid DMA fails synchronously with zero corruption;
stuck-busy latches freeze exactly one counter and are caught by tick
budgets; storms coalesce with strict ACK order 1, 2, 0; recovery uses the
two-step clear on every path.

## Full gates

```bash
ctest --test-dir soc_c/build --output-on-failure    # 9 suites: model + firmware link
ctest --test-dir firmware/build --output-on-failure # 9 suites: drivers/HAL/ISR/boot
```

## honesty rules (all experiments)

* **measured**: ticks/counters/registers read from the model.
* **derived**: arithmetic on measured values (throughput, speedup, latencies).
* **modeled**: wait/timing/budget assumptions stated in each doc.
* Wording is always “within the virtual SoC timing model” — never ARM/MCU/
  silicon performance.
