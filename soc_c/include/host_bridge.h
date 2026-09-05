/* Host bridge: route firmware HAL/MMIO traffic into a live soc_c instance.
 *
 * This is the unification point of the full-C migration: instead of the
 * simplified static-table shim (firmware/drivers/mmio.c, immediate
 * loopback, no timing), firmware drivers talk to the real behavioral
 * model (uart latency, timer countdown, DMA engine, INTC priority).
 *
 * Unit tests keep mmio.c (pure logic, no timing). System tests link
 * hal-hal.c plus drivers plus this bridge (no mmio.c) and step explicitly.
 */
#ifndef SOC_C_HOST_BRIDGE_H
#define SOC_C_HOST_BRIDGE_H

#include <stdint.h>

#include "soc.h"

/* Global live instance (single SoC, like silicon). */
soc_t *soc_host_soc(void);
void soc_host_init(const soc_config_t *cfg);
void soc_host_boot(void);
void soc_host_step(uint32_t n);

/* MMIO shim API (same signatures as firmware/drivers/mmio.c). */
uint32_t vlab_mmio_read(uint32_t addr);
void vlab_mmio_write(uint32_t addr, uint32_t val);
void vlab_mmio_consume_rx(void);

/* Test hooks backed by the real model. */
void vlab_test_raise_irq(uint32_t line);
void vlab_test_dma_complete(void);
void vlab_test_dma_error(uint32_t code);

#endif /* SOC_C_HOST_BRIDGE_H */
