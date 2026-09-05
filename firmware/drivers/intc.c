#include "driver_api.h"
#include "soc_regs.h"

void intc_enable(uint32_t mask) {
    vlab_mmio_write(VLAB_INTC_ENABLE, mask & 0x7U);
}

uint32_t intc_ack(void) { return vlab_mmio_read(VLAB_INTC_ACK); }

void intc_clear(uint32_t irq) { vlab_mmio_write(VLAB_INTC_CLEAR, irq); }
