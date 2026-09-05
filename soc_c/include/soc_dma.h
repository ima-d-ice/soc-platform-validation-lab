/* DMA engine: burst transfer + completion/error IRQ.
 * Mirrors soc/peripherals/dma/__init__.py + caps.py behavior.
 *
 * Single channel. CTRL.START auto-clears, STATUS sticky until next START
 * or IRQ_CLEAR, memmove semantics for overlap. Burst size is config-only.
 * Timing: ticks = words*latency_per_word + (bursts-1), bursts=ceil(w/burst).
 */
#ifndef SOC_C_DMA_H
#define SOC_C_DMA_H

#include <stdint.h>

#include "soc_bus.h"

#define SOC_DMA_SRC_OFF 0x00
#define SOC_DMA_DST_OFF 0x04
#define SOC_DMA_LEN_OFF 0x08
#define SOC_DMA_CTRL_OFF 0x0C
#define SOC_DMA_STATUS_OFF 0x10
#define SOC_DMA_IRQ_CLEAR_OFF 0x14
#define SOC_DMA_ERR_CODE_OFF 0x18

#define SOC_DMA_CTRL_START (1U << 0)
#define SOC_DMA_CTRL_IRQ_ENABLE (1U << 1)

#define SOC_DMA_STATUS_BUSY (1U << 0)
#define SOC_DMA_STATUS_DONE (1U << 1)
#define SOC_DMA_STATUS_ERROR (1U << 2)

#define SOC_DMA_ERR_NONE 0
#define SOC_DMA_ERR_ADDR 1
#define SOC_DMA_ERR_ALIGN 2
#define SOC_DMA_ERR_LEN 3
#define SOC_DMA_ERR_UNSUPPORTED 4

#define SOC_DMA_IRQ_LINE 2

struct soc_perf_t;
struct soc_intc_t;

/* Minimal region view for endpoint classification (avoids pulling
 * firmware headers into soc_c; layout matches mem_regions.h). */
typedef enum {
    SOC_RTYPE_ROM = 0,
    SOC_RTYPE_SRAM,
    SOC_RTYPE_DRAM,
    SOC_RTYPE_MMIO,
    SOC_RTYPE_PERIPHERAL
} soc_rtype_t;

typedef struct {
    const char *name;
    uint32_t base;
    uint32_t size;
    soc_rtype_t type;
} soc_region_t;

typedef struct {
    uint32_t alignment;
    uint32_t max_transfer; /* 0 = unlimited */
    int supports_ram_to_ram;
    int supports_mem_to_periph;
    int supports_periph_to_mem;
} soc_dma_caps_t;

typedef struct soc_dma_t soc_dma_t;
/* SRAM bridge without import cycles. Return SOC_OK or SOC_ERR_BUS. */
typedef int (*soc_dma_reader_t)(void *ctx, uint32_t addr, uint32_t len,
                                uint8_t *out);
typedef int (*soc_dma_writer_t)(void *ctx, uint32_t addr,
                                const uint8_t *payload, uint32_t len);

struct soc_dma_t {
    uint32_t sram_base;
    uint32_t sram_size;
    uint32_t latency_per_word;
    uint32_t burst;
    const soc_region_t *regions;
    uint32_t n_regions;
    soc_dma_caps_t caps;
    int irq_line;
    struct soc_intc_t *intc;
    struct soc_perf_t *perf;
    soc_dma_reader_t reader;
    soc_dma_writer_t writer;
    void *mem_ctx;
    uint32_t src;
    uint32_t dst;
    uint32_t length;
    uint32_t ctrl;
    int busy;
    int done;
    int error;
    uint32_t err_code;
    int32_t remaining;
    int irq_enable_latched;
    int fault_stuck_busy;
};

void soc_dma_init(soc_dma_t *d, uint32_t sram_base, uint32_t sram_size,
                  uint32_t latency_per_word, uint32_t burst,
                  const soc_region_t *regions, uint32_t n_regions,
                  const soc_dma_caps_t *caps, int irq_line,
                  struct soc_intc_t *intc, struct soc_perf_t *perf,
                  soc_dma_reader_t reader, soc_dma_writer_t writer,
                  void *mem_ctx);
void soc_dma_reset(soc_dma_t *d);
int soc_dma_read(soc_dma_t *d, uint32_t offset, uint32_t *out);
int soc_dma_write(soc_dma_t *d, uint32_t offset, uint32_t value);
void soc_dma_step(soc_dma_t *d);

#endif /* SOC_C_DMA_H */
