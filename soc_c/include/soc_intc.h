/* Interrupt controller: enable/pending/active + read-to-ack.
 * Mirrors soc/peripherals/intc/__init__.py.
 * Fixed priority: TIMER(1) > DMA(2) > UART(0). Non-preemptive, queued.
 */
#ifndef SOC_C_INTC_H
#define SOC_C_INTC_H

#include <stdint.h>

#include "soc_bus.h"

#define SOC_INTC_ENABLE_OFF 0x00
#define SOC_INTC_PENDING_OFF 0x04
#define SOC_INTC_ACK_OFF 0x08
#define SOC_INTC_CLEAR_OFF 0x0C
#define SOC_INTC_ACTIVE_OFF 0x10

#define SOC_IRQ_UART 0
#define SOC_IRQ_TIMER 1
#define SOC_IRQ_DMA 2
#define SOC_IRQ_NONE 0xFFFFFFFFU
#define SOC_N_LINES 3

struct soc_perf_t;

typedef struct soc_intc_t {
    uint32_t enable;
    uint32_t pending;
    uint32_t active;
    struct soc_perf_t *perf;
} soc_intc_t;

void soc_intc_init(soc_intc_t *ic, struct soc_perf_t *perf);
void soc_intc_reset(soc_intc_t *ic);
void soc_intc_raise(soc_intc_t *ic, int line);
int soc_intc_read(soc_intc_t *ic, uint32_t offset, uint32_t *out);
int soc_intc_write(soc_intc_t *ic, uint32_t offset, uint32_t value);

#endif /* SOC_C_INTC_H */
