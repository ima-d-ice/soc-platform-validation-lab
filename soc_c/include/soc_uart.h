/* UART loopback model with busy latency + RX completion IRQ (line 0).
 * Mirrors soc/peripherals/uart/__init__.py.
 */
#ifndef SOC_C_UART_H
#define SOC_C_UART_H

#include <stdint.h>

#include "soc_bus.h"

#define SOC_UART_TXDATA_OFF 0x00
#define SOC_UART_RXDATA_OFF 0x04
#define SOC_UART_STATUS_OFF 0x08
#define SOC_UART_CTRL_OFF 0x0C
#define SOC_UART_BAUDDIV_OFF 0x10

#define SOC_UART_STATUS_TX_BUSY (1U << 0)
#define SOC_UART_STATUS_TX_EMPTY (1U << 1)
#define SOC_UART_STATUS_RX_VALID (1U << 2)
#define SOC_UART_CTRL_ENABLE (1U << 0)

#define SOC_UART_ERR_DISABLED (-1)
#define SOC_UART_IRQ_LINE 0

/* DMA-visible stream FIFOs (model depth, not registers). uart-tx is the
 * DMA sink (RAM -> Peripheral), uart-rx the DMA source (Peripheral ->
 * RAM). Capacity equals the default max transfer; validated transfers
 * always fit. CPU single-byte loopback (_txdata/_rxdata/_rx_valid) is
 * unchanged; completions also append to the stream FIFOs so both paths
 * observe looped-back bytes. */
#define SOC_UART_DMA_FIFO_SIZE 16384U

struct soc_perf_t;
struct soc_intc_t;

typedef struct soc_uart_t {
    uint32_t latency_ticks;
    struct soc_perf_t *perf;
    struct soc_intc_t *intc;
    uint32_t ctrl;
    uint32_t bauddiv;
    uint32_t txdata;
    uint32_t rxdata;
    int32_t busy;
    int rx_valid;
    int fault_stuck_busy;
    uint8_t dma_tx_fifo[SOC_UART_DMA_FIFO_SIZE];
    uint32_t dma_tx_len;
    uint8_t dma_rx_fifo[SOC_UART_DMA_FIFO_SIZE];
    uint32_t dma_rx_len;
} soc_uart_t;

void soc_uart_init(soc_uart_t *u, uint32_t latency_ticks,
                   struct soc_perf_t *perf, struct soc_intc_t *intc);
void soc_uart_reset(soc_uart_t *u);
int soc_uart_read(soc_uart_t *u, uint32_t offset, uint32_t *out);
/* Returns 0 ok, SOC_UART_ERR_DISABLED if TX while disabled. */
int soc_uart_write(soc_uart_t *u, uint32_t offset, uint32_t value);
void soc_uart_step(soc_uart_t *u);

/* DMA stream FIFO helpers. Appends saturate at capacity (validated
 * transfers always fit; only un-drained loopback accumulation saturates).
 * Drain of a short FIFO zero-pads; tests must pre-fill exact lengths. */
void soc_uart_dma_tx_append(soc_uart_t *u, const uint8_t *payload,
                            uint32_t len);
void soc_uart_dma_rx_drain(soc_uart_t *u, uint8_t *out, uint32_t len);

#endif /* SOC_C_UART_H */
