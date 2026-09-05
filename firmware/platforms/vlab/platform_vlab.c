/* VLAB platform configuration data. See platform_vlab.h. */
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
    false, /* supports_mem_to_periph */
    false, /* supports_periph_to_mem */
    true,  /* supports_interrupts */
    false  /* supports_cancel */
};

static const struct irq_map s_vlab_irq_map = {
    VLAB_IRQ_UART, VLAB_IRQ_TIMER, VLAB_IRQ_DMA
};

const struct memory_region *vlab_memory_map(uint32_t *n) {
    if (n) *n = (uint32_t)(sizeof(s_vlab_map) / sizeof(s_vlab_map[0]));
    return s_vlab_map;
}

const struct dma_caps *vlab_dma_caps(void) { return &s_vlab_dma_caps; }

const struct irq_map *vlab_irq_map(void) { return &s_vlab_irq_map; }
