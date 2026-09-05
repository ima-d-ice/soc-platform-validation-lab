#ifndef VLAB_DRIVER_API_H
#define VLAB_DRIVER_API_H

#include <stddef.h>
#include <stdint.h>

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

/* DMA. Returns 0 ok, negative on validation error (mirrors ERR_CODE). */
#define VLAB_DMA_OK 0
#define VLAB_DMA_ERR_ADDR (-1)
#define VLAB_DMA_ERR_ALIGN (-2)
#define VLAB_DMA_ERR_LEN (-3)
#define VLAB_DMA_ERR_BUSY (-4)
int dma_start(uint32_t src, uint32_t dst, uint32_t len, int irq_enable);
uint32_t dma_status(void);
void dma_clear(void);
uint32_t dma_err_code(void);

/* Boot. */
int boot_init(void);

#endif /* VLAB_DRIVER_API_H */
