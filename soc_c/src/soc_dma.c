#include "soc_dma.h"

#include <stdlib.h>
#include <string.h>

#include "soc_intc.h"
#include "soc_perf.h"

static int soc_region_contains(const soc_region_t *r, uint32_t addr,
                               uint32_t len) {
    uint64_t end;
    if (!r || len == 0) return 0;
    end = (uint64_t)addr + (uint64_t)len;
    if (end > 0x100000000ULL) return 0;
    return addr >= r->base && end <= (uint64_t)r->base + (uint64_t)r->size;
}

static const soc_region_t *soc_find_region(const soc_region_t *table,
                                           uint32_t n, uint32_t addr,
                                           uint32_t len) {
    uint32_t i;
    if (!table) return NULL;
    for (i = 0; i < n; i++) {
        if (soc_region_contains(&table[i], addr, len)) return &table[i];
    }
    return NULL;
}

/* Endpoint classes: 0=MEM, 1=PERIPHERAL, 2=DEVICE, -1=unmapped */
static int soc_endpoint_type(const soc_region_t *regions, uint32_t n,
                             uint32_t addr, uint32_t len) {
    const soc_region_t *r = soc_find_region(regions, n, addr, len);
    if (!r) return -1;
    if (r->type == SOC_RTYPE_SRAM || r->type == SOC_RTYPE_DRAM) return 0;
    if (r->type == SOC_RTYPE_MMIO || r->type == SOC_RTYPE_PERIPHERAL) return 1;
    return 2;
}

static int soc_direction_supported(const soc_dma_caps_t *caps, int src,
                                   int dst) {
    if (src == 0 && dst == 0) return caps->supports_ram_to_ram;
    if (src == 0 && (dst == 1 || dst == 2))
        return caps->supports_mem_to_periph;
    if ((src == 1 || src == 2) && dst == 0)
        return caps->supports_periph_to_mem;
    return 0;
}

void soc_dma_init(soc_dma_t *d, uint32_t sram_base, uint32_t sram_size,
                  uint32_t latency_per_word, uint32_t burst,
                  const soc_region_t *regions, uint32_t n_regions,
                  const soc_dma_caps_t *caps, int irq_line,
                  struct soc_intc_t *intc, struct soc_perf_t *perf,
                  soc_dma_reader_t reader, soc_dma_writer_t writer,
                  void *mem_ctx) {
    d->sram_base = sram_base;
    d->sram_size = sram_size;
    d->latency_per_word = latency_per_word > 0 ? latency_per_word : 1;
    d->burst = burst > 0 ? burst : 1;
    d->regions = regions;
    d->n_regions = n_regions;
    if (caps)
        d->caps = *caps;
    else {
        d->caps.alignment = 4;
        d->caps.max_transfer = 0;
        d->caps.supports_ram_to_ram = 1;
        d->caps.supports_mem_to_periph = 0;
        d->caps.supports_periph_to_mem = 0;
    }
    d->irq_line = irq_line;
    d->intc = intc;
    d->perf = perf;
    d->reader = reader;
    d->writer = writer;
    d->mem_ctx = mem_ctx;
    d->src = 0;
    d->dst = 0;
    d->length = 0;
    d->ctrl = 0;
    d->busy = 0;
    d->done = 0;
    d->error = 0;
    d->err_code = SOC_DMA_ERR_NONE;
    d->remaining = 0;
    d->irq_enable_latched = 0;
    d->fault_stuck_busy = 0;
}

void soc_dma_reset(soc_dma_t *d) {
    d->src = 0;
    d->dst = 0;
    d->length = 0;
    d->ctrl = 0;
    d->busy = 0;
    d->done = 0;
    d->error = 0;
    d->err_code = SOC_DMA_ERR_NONE;
    d->remaining = 0;
    d->irq_enable_latched = 0;
    d->fault_stuck_busy = 0;
}

int soc_dma_read(soc_dma_t *d, uint32_t offset, uint32_t *out) {
    uint32_t s;
    switch (offset) {
        case SOC_DMA_SRC_OFF: *out = d->src; return SOC_OK;
        case SOC_DMA_DST_OFF: *out = d->dst; return SOC_OK;
        case SOC_DMA_LEN_OFF: *out = d->length; return SOC_OK;
        case SOC_DMA_CTRL_OFF: *out = d->ctrl; return SOC_OK;
        case SOC_DMA_STATUS_OFF:
            s = 0;
            if (d->busy) s |= SOC_DMA_STATUS_BUSY;
            if (d->done) s |= SOC_DMA_STATUS_DONE;
            if (d->error) s |= SOC_DMA_STATUS_ERROR;
            *out = s;
            return SOC_OK;
        case SOC_DMA_ERR_CODE_OFF: *out = d->err_code; return SOC_OK;
        case SOC_DMA_IRQ_CLEAR_OFF: return SOC_ERR_BUS;
        default: return SOC_ERR_BUS;
    }
}

static void soc_dma_fail(soc_dma_t *d, uint32_t code) {
    d->busy = 0;
    d->done = 0;
    d->error = 1;
    d->err_code = code;
    if (d->irq_enable_latched && d->intc)
        soc_intc_raise(d->intc, d->irq_line);
}

static void soc_dma_start(soc_dma_t *d, int irq_enable) {
    uint32_t align;
    int src_type, dst_type;
    uint32_t words, bursts;
    if (d->busy) {
        if (d->perf) soc_perf_count_stall(d->perf, 1);
        return;
    }
    d->irq_enable_latched = irq_enable ? 1 : 0;
    d->done = 0;
    d->error = 0;
    d->err_code = SOC_DMA_ERR_NONE;
    align = d->caps.alignment > 1 ? d->caps.alignment : 1;
    if (d->length == 0 || (align > 1 && d->length % align != 0)) {
        soc_dma_fail(d, SOC_DMA_ERR_LEN);
        return;
    }
    if (align > 1 && (d->src % align != 0 || d->dst % align != 0)) {
        soc_dma_fail(d, SOC_DMA_ERR_ALIGN);
        return;
    }
    if (d->caps.max_transfer != 0 && d->length > d->caps.max_transfer) {
        soc_dma_fail(d, SOC_DMA_ERR_UNSUPPORTED);
        return;
    }
    src_type = soc_endpoint_type(d->regions, d->n_regions, d->src, d->length);
    dst_type = soc_endpoint_type(d->regions, d->n_regions, d->dst, d->length);
    if (src_type < 0 || dst_type < 0) {
        soc_dma_fail(d, SOC_DMA_ERR_ADDR);
        return;
    }
    if (!soc_direction_supported(&d->caps, src_type, dst_type)) {
        soc_dma_fail(d, SOC_DMA_ERR_UNSUPPORTED);
        return;
    }
    d->busy = 1;
    words = (d->length + 3) / 4;
    bursts = (words + d->burst - 1) / d->burst;
    d->remaining = (int32_t)(words * d->latency_per_word + (bursts - 1));
    if (d->remaining < 1) d->remaining = 1;
}

int soc_dma_write(soc_dma_t *d, uint32_t offset, uint32_t value) {
    int irq_en;
    switch (offset) {
        case SOC_DMA_SRC_OFF: d->src = value; return SOC_OK;
        case SOC_DMA_DST_OFF: d->dst = value; return SOC_OK;
        case SOC_DMA_LEN_OFF: d->length = value; return SOC_OK;
        case SOC_DMA_CTRL_OFF:
            irq_en = (value & SOC_DMA_CTRL_IRQ_ENABLE) ? 1 : 0;
            if (value & SOC_DMA_CTRL_START) soc_dma_start(d, irq_en);
            d->ctrl = (value & ~SOC_DMA_CTRL_START) |
                      (irq_en ? SOC_DMA_CTRL_IRQ_ENABLE : 0U);
            return SOC_OK;
        case SOC_DMA_IRQ_CLEAR_OFF:
            d->done = 0;
            d->error = 0;
            d->err_code = SOC_DMA_ERR_NONE;
            return SOC_OK;
        case SOC_DMA_STATUS_OFF:
        case SOC_DMA_ERR_CODE_OFF:
            return SOC_ERR_BUS;
        default: return SOC_ERR_BUS;
    }
}

void soc_dma_step(soc_dma_t *d) {
    uint8_t *tmp;
    int rc;
    if (!d->busy) return;
    if (d->fault_stuck_busy) return;
    d->remaining--;
    if (d->remaining > 0) return;
    /* memmove semantics via temp buffer; post-START faults -> ERR_ADDR */
    if (!d->reader || !d->writer) return;
    tmp = (uint8_t *)malloc(d->length ? d->length : 1);
    if (!tmp) return;
    rc = d->reader(d->mem_ctx, d->src, d->length, tmp);
    if (rc != SOC_OK) {
        free(tmp);
        d->busy = 0;
        d->done = 0;
        d->error = 1;
        d->err_code = SOC_DMA_ERR_ADDR;
        if (d->irq_enable_latched && d->intc)
            soc_intc_raise(d->intc, d->irq_line);
        return;
    }
    rc = d->writer(d->mem_ctx, d->dst, tmp, d->length);
    free(tmp);
    if (rc != SOC_OK) {
        d->busy = 0;
        d->done = 0;
        d->error = 1;
        d->err_code = SOC_DMA_ERR_ADDR;
        if (d->irq_enable_latched && d->intc)
            soc_intc_raise(d->intc, d->irq_line);
        return;
    }
    d->busy = 0;
    d->done = 1;
    d->error = 0;
    if (d->perf) soc_perf_count_dma(d->perf, d->length);
    if (d->irq_enable_latched && d->intc)
        soc_intc_raise(d->intc, d->irq_line);
}
