# Limitations (virtual-model honesty statement)

This is a host-native behavioral virtual SoC written in C. It is
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
7. **Scope bounds.** No RTOS/Linux models (removed in the pure-C
   migration; prior Python-era studies remain in git history), no new
   peripherals, no RTL — deliberate; the studied surface is platform
   software + validation.
8. **No RTOS port.** There is deliberately no POSIX/FreeRTOS port: a
   wall-clock port would break run-to-run determinism, which every CTest
   in this repo guarantees.
9. **No Linux layer.** There is no kernel or userspace Linux driver
   model in this tree.
10. **Single DMA channel.** No overlapped transfers. The `soc_c_cpu_vs_dma`
    bench uses SRC @+0x0000 / DST @+0x8000 inside 64KB SRAM, capping
    single transfers at 16KB.
