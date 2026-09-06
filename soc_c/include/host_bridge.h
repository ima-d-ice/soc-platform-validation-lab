/* Host bridge: route firmware HAL traffic into one live SoC instance.
 *
 * The single register path for host execution: firmware drivers talk to
 * the real ticking model (uart latency, timer countdown, DMA engine, INTC
 * priority) through HAL. Tests boot/step the model explicitly.
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

/* MMIO access into the live model (implements driver_api.h). */
uint32_t vlab_mmio_read(uint32_t addr);
void vlab_mmio_write(uint32_t addr, uint32_t val);

/* Test hooks backed by the real model. */
void vlab_test_raise_irq(uint32_t line);
void vlab_test_dma_complete(void);
void vlab_test_dma_error(uint32_t code);

#endif /* SOC_C_HOST_BRIDGE_H */
