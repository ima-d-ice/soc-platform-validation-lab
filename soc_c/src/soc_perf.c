#include "soc_perf.h"

void soc_perf_init(soc_perf_t *p) {
    p->cycles = 0;
    p->mem_acc = 0;
    p->dma_bytes = 0;
    p->irq_count = 0;
    p->stalls = 0;
    p->enabled = 0;
    p->ctrl = 0;
}

void soc_perf_reset_counters(soc_perf_t *p) {
    p->cycles = 0;
    p->mem_acc = 0;
    p->dma_bytes = 0;
    p->irq_count = 0;
    p->stalls = 0;
}

void soc_perf_tick(soc_perf_t *p) {
    if (p->enabled) p->cycles++;
}

void soc_perf_count_mem(soc_perf_t *p) {
    if (p->enabled) p->mem_acc++;
}

void soc_perf_count_stall(soc_perf_t *p, uint32_t n) {
    if (p->enabled) p->stalls += n;
}

void soc_perf_count_dma(soc_perf_t *p, uint32_t nbytes) {
    if (p->enabled) p->dma_bytes += nbytes;
}

void soc_perf_count_irq(soc_perf_t *p) {
    if (p->enabled) p->irq_count++;
}

int soc_perf_read(soc_perf_t *p, uint32_t offset, uint32_t *out) {
    switch (offset) {
        case SOC_PERF_CYCLES_OFF: *out = p->cycles; return SOC_OK;
        case SOC_PERF_MEM_ACC_OFF: *out = p->mem_acc; return SOC_OK;
        case SOC_PERF_DMA_BYTES_OFF: *out = p->dma_bytes; return SOC_OK;
        case SOC_PERF_IRQ_COUNT_OFF: *out = p->irq_count; return SOC_OK;
        case SOC_PERF_STALLS_OFF: *out = p->stalls; return SOC_OK;
        case SOC_PERF_CTRL_OFF: *out = p->ctrl; return SOC_OK;
        default: return SOC_ERR_BUS;
    }
}

int soc_perf_write(soc_perf_t *p, uint32_t offset, uint32_t value) {
    switch (offset) {
        case SOC_PERF_CYCLES_OFF: p->cycles = value; return SOC_OK;
        case SOC_PERF_MEM_ACC_OFF: p->mem_acc = value; return SOC_OK;
        case SOC_PERF_DMA_BYTES_OFF: p->dma_bytes = value; return SOC_OK;
        case SOC_PERF_IRQ_COUNT_OFF: p->irq_count = value; return SOC_OK;
        case SOC_PERF_STALLS_OFF: p->stalls = value; return SOC_OK;
        case SOC_PERF_CTRL_OFF:
            p->ctrl = value;
            p->enabled = (value & SOC_PERF_CTRL_ENABLE) ? 1 : 0;
            if (value & SOC_PERF_CTRL_RESET) soc_perf_reset_counters(p);
            return SOC_OK;
        default: return SOC_ERR_BUS;
    }
}
