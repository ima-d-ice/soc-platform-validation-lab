#include "driver_api.h"
#include "hal.h"
#include "soc_regs.h"

/* Consume helper from mmio.c (host shim). On silicon, RX_VALID clears on
 * RXDATA read in hardware. */
void vlab_mmio_consume_rx(void);

int uart_init(uint32_t bauddiv) {
    hal_write_reg(VLAB_UART_BAUDDIV, bauddiv);
    hal_write_reg(VLAB_UART_CTRL, VLAB_UART_CTRL_ENABLE);
    return VLAB_UART_OK;
}

uint32_t uart_status(void) { return hal_read_reg(VLAB_UART_STATUS); }

int uart_write_byte(uint8_t b) {
    uint32_t ctrl = hal_read_reg(VLAB_UART_CTRL);
    if (!(ctrl & VLAB_UART_CTRL_ENABLE)) return VLAB_UART_ERR_DISABLED;
    /* Poll TX_EMPTY with a bounded timeout (host shim: always ready). */
    for (int i = 0; i < 1000; i++) {
        uint32_t st = hal_read_reg(VLAB_UART_STATUS);
        if (st & VLAB_UART_STATUS_TX_EMPTY) break;
        if (i == 999) return VLAB_UART_ERR_TIMEOUT;
    }
    hal_write_reg(VLAB_UART_TXDATA, (uint32_t)b);
    return VLAB_UART_OK;
}

int uart_read_byte(uint8_t *out) {
    uint32_t st = hal_read_reg(VLAB_UART_STATUS);
    if (!(st & VLAB_UART_STATUS_RX_VALID)) return VLAB_UART_ERR_TIMEOUT;
    uint32_t v = hal_read_reg(VLAB_UART_RXDATA);
    vlab_mmio_consume_rx();
    if (out) *out = (uint8_t)(v & 0xFFU);
    return VLAB_UART_OK;
}
