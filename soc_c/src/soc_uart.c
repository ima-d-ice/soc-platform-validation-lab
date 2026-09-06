#include "soc.h"

#include <string.h>

void soc_uart_init(soc_uart_t *u, uint32_t latency_ticks,
                   struct soc_perf_t *perf, struct soc_intc_t *intc) {
    u->latency_ticks = latency_ticks;
    u->perf = perf;
    u->intc = intc;
    u->ctrl = 0;
    u->bauddiv = 0;
    u->txdata = 0;
    u->rxdata = 0;
    u->busy = 0;
    u->rx_valid = 0;
    u->fault_stuck_busy = 0;
    u->dma_tx_len = 0;
    u->dma_rx_len = 0;
}

void soc_uart_reset(soc_uart_t *u) {
    u->ctrl = 0;
    u->bauddiv = 0;
    u->txdata = 0;
    u->rxdata = 0;
    u->busy = 0;
    u->rx_valid = 0;
    u->fault_stuck_busy = 0;
    u->dma_tx_len = 0;
    u->dma_rx_len = 0;
}

static uint32_t soc_uart_status(soc_uart_t *u) {
    uint32_t s = 0;
    if (u->busy > 0)
        s |= SOC_UART_STATUS_TX_BUSY;
    else
        s |= SOC_UART_STATUS_TX_EMPTY;
    if (u->rx_valid) s |= SOC_UART_STATUS_RX_VALID;
    return s;
}

int soc_uart_read(soc_uart_t *u, uint32_t offset, uint32_t *out) {
    switch (offset) {
        case SOC_UART_TXDATA_OFF: return SOC_ERR_BUS;
        case SOC_UART_RXDATA_OFF:
            *out = u->rxdata & 0xFFU;
            u->rx_valid = 0;
            return SOC_OK;
        case SOC_UART_STATUS_OFF: *out = soc_uart_status(u); return SOC_OK;
        case SOC_UART_CTRL_OFF: *out = u->ctrl; return SOC_OK;
        case SOC_UART_BAUDDIV_OFF: *out = u->bauddiv; return SOC_OK;
        default: return SOC_ERR_BUS;
    }
}

int soc_uart_write(soc_uart_t *u, uint32_t offset, uint32_t value) {
    switch (offset) {
        case SOC_UART_TXDATA_OFF:
            if (!(u->ctrl & SOC_UART_CTRL_ENABLE)) {
                if (u->perf) soc_perf_count_stall(u->perf, 1);
                return SOC_UART_ERR_DISABLED;
            }
            u->txdata = value & 0xFFU;
            u->busy = (u->latency_ticks > 0) ? (int32_t)u->latency_ticks : 1;
            return SOC_OK;
        case SOC_UART_CTRL_OFF: u->ctrl = value; return SOC_OK;
        case SOC_UART_BAUDDIV_OFF: u->bauddiv = value; return SOC_OK;
        case SOC_UART_RXDATA_OFF:
        case SOC_UART_STATUS_OFF:
            return SOC_ERR_BUS;
        default: return SOC_ERR_BUS;
    }
}

void soc_uart_step(soc_uart_t *u) {
    if (u->busy > 0) {
        if (u->fault_stuck_busy) return;
        u->busy--;
        if (u->busy == 0) {
            uint8_t b;
            u->rxdata = u->txdata;
            u->rx_valid = 1;
            /* Loopback is also visible to the DMA streams (tx record +
             * rx stream); the helper appends to both exactly once. */
            b = (uint8_t)(u->txdata & 0xFFU);
            soc_uart_dma_tx_append(u, &b, 1);
            if (u->intc) soc_intc_raise(u->intc, SOC_UART_IRQ_LINE);
        }
    }
}

void soc_uart_dma_tx_append(soc_uart_t *u, const uint8_t *payload,
                            uint32_t len) {
    uint32_t space, n;
    if (!payload || len == 0) return;
    space = (u->dma_tx_len < SOC_UART_DMA_FIFO_SIZE)
                ? SOC_UART_DMA_FIFO_SIZE - u->dma_tx_len
                : 0;
    n = (len < space) ? len : space;
    if (n > 0) {
        memcpy(&u->dma_tx_fifo[u->dma_tx_len], payload, n);
        u->dma_tx_len += n;
    }
    /* Loopback: sunk bytes reappear on the RX stream. */
    space = (u->dma_rx_len < SOC_UART_DMA_FIFO_SIZE)
                ? SOC_UART_DMA_FIFO_SIZE - u->dma_rx_len
                : 0;
    n = (len < space) ? len : space;
    if (n > 0) {
        memcpy(&u->dma_rx_fifo[u->dma_rx_len], payload, n);
        u->dma_rx_len += n;
    }
}

void soc_uart_dma_rx_drain(soc_uart_t *u, uint8_t *out, uint32_t len) {
    uint32_t n;
    if (!out || len == 0) return;
    n = (len < u->dma_rx_len) ? len : u->dma_rx_len;
    if (n > 0) {
        memcpy(out, u->dma_rx_fifo, n);
        memmove(u->dma_rx_fifo, &u->dma_rx_fifo[n], u->dma_rx_len - n);
        u->dma_rx_len -= n;
    }
    if (n < len) memset(&out[n], 0, len - n); /* short read zero-pads */
}
