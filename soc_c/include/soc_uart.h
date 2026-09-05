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
} soc_uart_t;

void soc_uart_init(soc_uart_t *u, uint32_t latency_ticks,
                   struct soc_perf_t *perf, struct soc_intc_t *intc);
void soc_uart_reset(soc_uart_t *u);
int soc_uart_read(soc_uart_t *u, uint32_t offset, uint32_t *out);
/* Returns 0 ok, SOC_UART_ERR_DISABLED if TX while disabled. */
int soc_uart_write(soc_uart_t *u, uint32_t offset, uint32_t value);
void soc_uart_step(soc_uart_t *u);

#endif /* SOC_C_UART_H */
