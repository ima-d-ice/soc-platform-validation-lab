#include "driver_api.h"
#include "hal.h"
#include "soc_regs.h"

/* UART RX completion raises its INTC line; delivery is gated solely by the
 * INTC enable mask (no per-UART IRQ bit; register map unchanged). */
void intc_enable(uint32_t mask) {
    hal_write_reg(VLAB_INTC_ENABLE, mask & 0x7U);
}

uint32_t intc_ack(void) { return hal_read_reg(VLAB_INTC_ACK); }

void intc_clear(uint32_t irq) { hal_write_reg(VLAB_INTC_CLEAR, irq); }
