# Experiments

Deterministic, model-tick experiments in this repository. Every number is
produced by running the listed binary against the virtual SoC timing
model; result output is reproducible and gitignored.

## Boot (`bench_boot`)

```bash
cmake -S . -B build && cmake --build build
./build/bench_boot
```

REAL OBSERVATION: Reset → main entry takes 5 model ticks (50 ns at the
informational 100 MHz), deterministic across runs. Gated by the
`test_boot` CTest.

## CPU vs DMA data path (`bench_dma`, see `docs/dma-optimization.md`)

```bash
./build/bench_dma   # CSV: size,burst,words,bursts,dma_ticks,cpu_ticks
```

REAL OBSERVATIONS: CPU copy costs 3 ticks/word (modeled wait); DMA follows
`words*1 + (bursts-1)` ticks; burst 1→16 cuts 16KB DMA ticks 8191→4351;
every cell byte-compares source vs destination (mismatch aborts non-zero).

## Fault injection (`test_faults` CTest, see `docs/fault-injection.md`)

```bash
ctest --test-dir build -R test_faults --output-on-failure
```

REAL OBSERVATIONS: invalid DMA fails synchronously with zero corruption;
stuck-busy latches freeze exactly one counter and are caught by tick
budgets; recovery uses the two-step clear on every path.

## Full gate

```bash
ctest --test-dir build --output-on-failure   # 15 suites: model + firmware + smoke
```

## honesty rules (all experiments)

* **measured**: ticks/counters/registers read from the model.
* **derived**: arithmetic on measured values (throughput, speedup, latencies).
* **modeled**: wait/timing/budget assumptions stated in each doc.
* Wording is always “within the virtual SoC timing model” — never ARM/MCU/
  silicon performance.
