/* ISR framework: vector table + dispatched interrupt handling.
 *
 * HOST HONESTY: on the host there is no preemptive interrupt hardware, so
 * ISRs do not fire asynchronously. Instead, host code calls isr_dispatch()
 * (typically from the main loop or a tick hook); dispatch reads INTC ACK
 * and invokes the registered handler for each pending line, highest
 * priority first. On silicon the same handlers would be installed in the
 * vector table and entered by hardware. Driver code (volatile flags,
 * critical sections, ACK/clear ordering) is written identically either way.
 */
#ifndef VLAB_ISR_H
#define VLAB_ISR_H

#include <stdint.h>

#include "soc_regs.h" /* VLAB_IRQ_UART/TIMER/DMA/NONE live here */

#define VLAB_IRQ_COUNT 3U

typedef void (*isr_handler_t)(uint32_t line);

/* Register (or unregister with NULL) the handler for an IRQ line. */
void isr_register(uint32_t line, isr_handler_t handler);

/* Dispatch all currently pending+enabled IRQs, highest priority first.
 * Always ACKs and clears each line (even with no handler registered, so a
 * stray IRQ can never wedge the controller). Returns lines handled.
 * Bounded: at most VLAB_IRQ_COUNT dispatches per call. */
int isr_dispatch(void);

/* Number of dispatched IRQs since boot (for tests/telemetry). */
uint32_t isr_dispatched_count(void);

#endif /* VLAB_ISR_H */
