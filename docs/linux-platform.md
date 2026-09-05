# Linux-Facing Platform Software (Phase 7)

> **What this is and is not.** `linux/` is a **userspace platform model**:
> host-Python code implementing the exact layering a Linux platform driver
> would use (application API → driver abstraction → MMIO layer → virtual
> device) against the virtual SoC. It is explicitly **not a Linux kernel
> driver**, not kernel code, and was never compiled against kernel headers.
> All numbers are virtual-model ticks.

## What is virtual / measured / derived / modeled

| Class | Content |
|---|---|
| **Virtual** | The device itself (frame source + DMA + IRQ path are SoC models); the “kernel boundary” (no syscalls, no real user/kernel split) |
| **Measured** | e2e ticks/frame, transfer ticks, MEM_ACC, DMA bytes, notifications, poll reads, queue high-water mark, refused submits, mismatches (always 0) |
| **Derived** | Throughput, p50/p99, means across reps |
| **Modeled** | Frame sizes/counts, ring depths, paced-consumer period (= expected transfer ticks), staging/arena SRAM layout, CPU fill of staging |

## What would change on real Linux hardware

Real syscalls + copy overhead, interrupt entry/exit cost, cache effects,
IOMMU/SMMU mapping instead of the identity arena, concurrent masters on
the bus, scheduler preemption of the driver thread, and power/clock
behavior — none of which exist here. Relative comparisons *inside* this
model (polling vs notification, depth scaling) are the valid takeaway.

## REAL OBSERVATIONS (`configs/base.yaml`, 5 reps, deterministic)

* **Buffer size:** deeper rings raise mean e2e latency (queue waits; e.g.
  64B: 36.4 → 134.6 ticks from depth 1→8) while absorbing bursts; depth-1
  halves throughput (~1.6 vs ~3.2 B/tick) because the producer stalls with
  nowhere to stage the next frame.
* **Polling vs notification:** identical e2e ticks at every cell (same
  model property as Phase 4 — combinational MMIO). The tradeoff is
  handling: polling burns N+1 STATUS reads per transfer with 0 IRQs;
  notification costs 3 MMIO ops + 1 IRQ per transfer. Neither is “faster”
  here; they differ in CPU attention, measured as reads vs IRQs.
* **Transfer size:** throughput converges to ~3.2 B/tick (depth ≥ 2) as
  per-transfer overhead amortizes; e2e latency scales linearly with size.
* **Integrity:** mismatches == 0 in all 200 cells; refused submits are
  producer backpressure (frames are retried, completions == submissions).
* **Arena cap (model fact):** the 32KB arena fits at most two 16KB
  buffers, so 16KB depth-4/8 rows behave as depth-2 plus extra refusals —
  visible as flat queue-depth lines, documented not hidden.

## Genuine model bug found and fixed in this phase

Post-START SRC corruption (validation probe, not a legal driver op)
escaped `Dma.step()` as an uncaught `BusError` out of the tick loop.
Fixed minimally: completion I/O faults now convert to ERROR/ERR_ADDR
deterministically (spec §5.3 ERR_ADDR semantics), with IRQ iff enabled.
All 98 pre-existing tests still pass; `soc-spec.md` §5.3 gains one
clarifying sentence (below).
