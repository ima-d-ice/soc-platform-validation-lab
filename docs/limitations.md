# Limitations (virtual-model honesty statement)

This is a host-native behavioral virtual SoC written in Python/C. It is
useful for firmware structure, driver sequencing, validation methodology,
and *relative* reasoning inside one consistent timing model. It is not a
performance oracle for any physical system.

1. **No silicon meaning.** Tick counts, speedups, latencies, and IRQ counts
   characterize this model under the stated config only. Never quote them
   as ARM/MCU/silicon timing, bus bandwidth, or interrupt latency.
2. **Combinational MMIO.** Register setup/ACK/clear accesses cost zero
   ticks (counted in MEM_ACC). Recovery latencies of 0 ticks and
   polling-vs-IRQ tick equality are consequences of this choice.
3. **Modeled waits.** CPU 3 ticks/word, DMA `words*1 + (bursts-1)` ticks,
   UART 5-tick latency, and all fault-detection budgets are chosen model
   parameters, recorded per run for auditability — not measurements of
   hardware.
4. **No contention or caches.** Single channel, no bus arbitration with
   other masters, no cache hierarchy, no pipelining, no clock-domain
   effects.
5. **Bounded fault classes.** Single-latch stuck faults only; no
   degraded/intermittent faults; no UNRECOVERABLE instance exists in the
   matrix yet (branch unit-tested only).
6. **Capacity bounds.** 64KB SRAM caps single transfers at 16KB; 64KB
   transfers are refused by a fit check rather than worked around.
7. **Scope bounds.** No Linux yet, no new peripherals, no RTL —
   deliberate; the studied surface is platform software + validation.
8. **RTOS is modeled, not ported.** `rtos/` implements FreeRTOS *scheduling
   semantics* on model ticks; it is not the FreeRTOS kernel, has no SysTick
   hardware, no ISR-driven preemption, no priority inheritance, and charges
   zero ticks per context switch. Relative scheduling comparisons inside
   the model are valid; absolute latency claims are not.
9. **Linux layer is userspace, not kernel.** `linux/` never runs in kernel
   mode, uses no syscalls/headers, has no IOMMU, caches, or concurrent bus
   masters. It validates driver *structure* (layering, completion paths,
   error handling) and relative tradeoffs, not kernel performance.
10. **Single DMA channel.** Pipelining is descriptor queueing, not overlapped
   transfers; ring depth absorbs producer bursts but cannot overlap engine
   time. The 32KB driver arena caps 16KB rows to two buffers (documented
   in the JSON-driving code and visible as flat queue-depth lines).
