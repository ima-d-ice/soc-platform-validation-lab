#include "driver_api.h"
#include "soc_regs.h"

#define TIMER_ENABLE (1U << 0)
#define TIMER_PERIODIC (1U << 1)
#define TIMER_IRQ_EN (1U << 2)

int timer_start(uint32_t load, int periodic, int irq_enable) {
    if (load == 0) return -1;
    vlab_mmio_write(VLAB_TIMER_LOAD, load);
    uint32_t ctrl = TIMER_ENABLE | (periodic ? TIMER_PERIODIC : 0U) |
                    (irq_enable ? TIMER_IRQ_EN : 0U);
    vlab_mmio_write(VLAB_TIMER_CTRL, ctrl);
    return 0;
}

void timer_stop(void) { vlab_mmio_write(VLAB_TIMER_CTRL, 0U); }

int timer_fired(void) {
    return (vlab_mmio_read(VLAB_TIMER_IRQ_STATUS) & 0x1U) ? 1 : 0;
}

void timer_clear(void) { vlab_mmio_write(VLAB_TIMER_IRQ_CLEAR, 0x1U); }

uint32_t timer_value(void) { return vlab_mmio_read(VLAB_TIMER_VALUE); }
