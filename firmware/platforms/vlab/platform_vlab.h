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

/* VLAB DMA capabilities: RAM->RAM, RAM->Peripheral and Peripheral->RAM,
 * 4-byte aligned, 16KB max, interrupts, no cancel. */
const struct dma_caps *vlab_dma_caps(void);

/* VLAB DMA-capable peripheral endpoints: UART TX FIFO (sink) and UART RX
 * FIFO (source). Every other mapped MMIO address is valid but NOT
 * DMA-capable (driver rejects it as UNSUPPORTED, never ADDR). */
const struct dma_periph_ep *vlab_dma_periph_eps(uint32_t *n);

/* VLAB IRQ assignment (matches the generated VLAB_IRQ_* defines). */
const struct irq_map *vlab_irq_map(void);

#endif /* VLAB_PLATFORM_VLAB_H */
