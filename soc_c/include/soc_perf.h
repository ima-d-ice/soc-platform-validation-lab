/* Performance monitor: real model counters (never synthesised).
 * Mirrors soc/peripherals/perf/__init__.py.
 */
#ifndef SOC_C_PERF_H
#define SOC_C_PERF_H

#include <stdint.h>

#include "soc_bus.h"

#define SOC_PERF_CYCLES_OFF 0x00
#define SOC_PERF_MEM_ACC_OFF 0x04
#define SOC_PERF_DMA_BYTES_OFF 0x08
#define SOC_PERF_IRQ_COUNT_OFF 0x0C
#define SOC_PERF_STALLS_OFF 0x10
#define SOC_PERF_CTRL_OFF 0x14

#define SOC_PERF_CTRL_ENABLE (1U << 0)
#define SOC_PERF_CTRL_RESET (1U << 1)

typedef struct soc_perf_t {
    uint32_t cycles;
    uint32_t mem_acc;
    uint32_t dma_bytes;
    uint32_t irq_count;
    uint32_t stalls;
    int enabled;
    uint32_t ctrl;
} soc_perf_t;

void soc_perf_init(soc_perf_t *p);
void soc_perf_reset_counters(soc_perf_t *p);
void soc_perf_tick(soc_perf_t *p);
void soc_perf_count_mem(soc_perf_t *p);
void soc_perf_count_stall(soc_perf_t *p, uint32_t n);
void soc_perf_count_dma(soc_perf_t *p, uint32_t nbytes);
void soc_perf_count_irq(soc_perf_t *p);
int soc_perf_read(soc_perf_t *p, uint32_t offset, uint32_t *out);
int soc_perf_write(soc_perf_t *p, uint32_t offset, uint32_t value);

#endif /* SOC_C_PERF_H */
