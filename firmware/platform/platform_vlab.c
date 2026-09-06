/* VLAB platform configuration data. See platform_vlab.h.
 *
 * Data only (no driver calls): this file links into the model library so
 * both the SoC and the drivers consume ONE table. Bring-up code lives in
 * platform_init.c (firmware library) to keep static linking acyclic.
 */
#include "platform_vlab.h"

#include "soc_regs.h"

static const struct memory_region s_vlab_map[] = {
    {"rom", VLAB_ROM_BASE, 16384U, MEM_TYPE_ROM, MEM_PERM_R | MEM_PERM_X},
    {"sram", VLAB_SRAM_BASE, 65536U, MEM_TYPE_SRAM, MEM_PERM_R | MEM_PERM_W},
    {"uart", VLAB_UART_BASE, 4096U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
    {"timer", VLAB_TIMER_BASE, 4096U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
    {"dma", VLAB_DMA_BASE, 4096U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
    {"intc", VLAB_INTC_BASE, 4096U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
    {"perf", VLAB_PERF_BASE, 4096U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
};

static const struct dma_caps s_vlab_dma_caps = {
    4U,    /* alignment */
    16384U, /* max_transfer */
    true,  /* supports_ram_to_ram */
    true,  /* supports_mem_to_periph */
    true,  /* supports_periph_to_mem */
    true,  /* supports_interrupts */
    false  /* supports_cancel */
};

/* DMA-capable FIFOs anchor at existing FIFO registers (no map change):
 * TXDATA accepts streamed bytes, RXDATA sources them. */
static const struct dma_periph_ep s_vlab_dma_periphs[] = {
    {"uart-tx", VLAB_UART_TXDATA, DMA_EP_DST},
    {"uart-rx", VLAB_UART_RXDATA, DMA_EP_SRC},
};

static const struct irq_map s_vlab_irq_map = {
    VLAB_IRQ_UART, VLAB_IRQ_TIMER, VLAB_IRQ_DMA
};

const struct memory_region *vlab_memory_map(uint32_t *n) {
    if (n) *n = (uint32_t)(sizeof(s_vlab_map) / sizeof(s_vlab_map[0]));
    return s_vlab_map;
}

const struct dma_caps *vlab_dma_caps(void) { return &s_vlab_dma_caps; }

const struct dma_periph_ep *vlab_dma_periph_eps(uint32_t *n) {
    if (n)
        *n = (uint32_t)(sizeof(s_vlab_dma_periphs) /
                        sizeof(s_vlab_dma_periphs[0]));
    return s_vlab_dma_periphs;
}

const struct irq_map *vlab_irq_map(void) { return &s_vlab_irq_map; }
