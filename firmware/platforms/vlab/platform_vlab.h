/* CURRENT VLAB PLATFORM: concrete configuration data.
 *
 * PLATFORM CONFIGURATION: the actual VLAB addresses, DMA capabilities, and
 * IRQ assignment. Generic code (drivers, HAL, ISR dispatcher) consumes
 * these tables; nothing outside platforms/ and the generated soc_regs.h
 * may hard-code VLAB addresses or capabilities.
 */
#ifndef VLAB_PLATFORM_VLAB_H
#define VLAB_PLATFORM_VLAB_H

#include <stdint.h>

#include "dma_caps.h"
#include "mem_regions.h"

struct irq_map {
    uint32_t uart_line;
    uint32_t timer_line;
    uint32_t dma_line;
};

/* VLAB memory map (matches configs/base.yaml + soc-spec.md). */
const struct memory_region *vlab_memory_map(uint32_t *n);

/* VLAB DMA capabilities: SRAM-only RAM-to-RAM, 4-byte aligned, 16KB max,
 * interrupts, no cancel. */
const struct dma_caps *vlab_dma_caps(void);

/* VLAB IRQ assignment (matches the generated VLAB_IRQ_* defines). */
const struct irq_map *vlab_irq_map(void);

#endif /* VLAB_PLATFORM_VLAB_H */
