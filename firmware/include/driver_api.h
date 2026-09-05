#ifndef VLAB_DRIVER_API_H
#define VLAB_DRIVER_API_H

#include <stddef.h>
#include <stdint.h>

#include "dma_caps.h"
#include "mem_regions.h"

/* MMIO (host shim in mmio.c; on silicon these are volatile accesses). */
uint32_t vlab_mmio_read(uint32_t addr);
void vlab_mmio_write(uint32_t addr, uint32_t val);

/* UART. Returns 0 ok, negative on error. */
#define VLAB_UART_OK 0
#define VLAB_UART_ERR_DISABLED (-1)
#define VLAB_UART_ERR_TIMEOUT (-2)
int uart_init(uint32_t bauddiv);
int uart_write_byte(uint8_t b);
int uart_read_byte(uint8_t *out);
uint32_t uart_status(void);

/* Timer. */
int timer_start(uint32_t load, int periodic, int irq_enable);
void timer_stop(void);
int timer_fired(void);
void timer_clear(void);
uint32_t timer_value(void);

/* INTC. Returns irq number or 0xFFFFFFFF when none. */
uint32_t intc_ack(void);
void intc_enable(uint32_t mask);
void intc_clear(uint32_t irq);

/* DMA. Returns 0 ok, negative on validation error (mirrors ERR_CODE).
 * VLAB_DMA_ERR_UNSUPPORTED mirrors register code 4: mapped but outside
 * the platform's DMA capabilities (vs ADDR = unmapped/invalid use). */
#define VLAB_DMA_OK 0
#define VLAB_DMA_ERR_ADDR (-1)
#define VLAB_DMA_ERR_ALIGN (-2)
#define VLAB_DMA_ERR_LEN (-3)
#define VLAB_DMA_ERR_BUSY (-4)
#define VLAB_DMA_ERR_UNSUPPORTED (-5)

/* DMA configuration: platform region table + capabilities. dma_init()
 * loads the VLAB platform defaults (call after boot, before use);
 * dma_configure() overrides with another platform's tables. */
void dma_init(void);
void dma_configure(const struct memory_region *map, uint32_t n,
                   const struct dma_caps *caps);
int dma_start(uint32_t src, uint32_t dst, uint32_t len, int irq_enable);
uint32_t dma_status(void);
void dma_clear(void);
uint32_t dma_err_code(void);

/* DMA interrupt-driven state machine (see isr.h for dispatch).
 * Lifecycle: IDLE -> STARTING -> ACTIVE -> COMPLETE -> (recover) -> IDLE,
 *                                  ACTIVE -> ERROR -> (recover) -> IDLE.
 * dma_submit requires IDLE and returns BUSY otherwise; completion and
 * errors are signalled by dma_isr (registered for VLAB_IRQ_DMA) which
 * performs the two-step clear. Shared ISR/main state is volatile and
 * submit/recover run under hal critical sections. */
typedef enum {
    DMA_S_IDLE = 0,
    DMA_S_STARTING,
    DMA_S_ACTIVE,
    DMA_S_COMPLETE,
    DMA_S_ERROR,
    DMA_S_RECOVERY
} dma_state_t;

int dma_submit(uint32_t src, uint32_t dst, uint32_t len, int irq_enable);
dma_state_t dma_state(void);

/* Main-line completion check: reads the volatile ISR-set flag, no bus
 * traffic. Returns nonzero once dma_isr has observed DONE. */
int dma_is_complete(void);

/* Latched error code captured by dma_isr (0 when no error). */
uint32_t dma_latched_error(void);

/* Number of DMA ISRs serviced (for tests/telemetry). */
uint32_t dma_irq_count(void);

/* ISR for the DMA line: ACK state, two-step clear, flag/state update. */
void dma_isr(uint32_t line);

/* ERROR or COMPLETE -> IDLE. Clears flags (two-step) and resets latches. */
void dma_recover(void);

/* Boot. */
int boot_init(void);

/* Host test hooks (tests only, backed by mmio.c): raise an IRQ line,
 * force DMA completion, or force a DMA error with the given code. */
void vlab_test_raise_irq(uint32_t line);
void vlab_test_dma_complete(void);
void vlab_test_dma_error(uint32_t code);

#endif /* VLAB_DRIVER_API_H */
