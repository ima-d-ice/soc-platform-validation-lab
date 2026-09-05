/* ISR dispatch implementation. See include/isr.h for the contract. */
#include "isr.h"

#include "driver_api.h"
#include "hal.h"
#include "soc_regs.h"

static isr_handler_t s_vectors[VLAB_IRQ_COUNT] = {0, 0, 0};
static volatile uint32_t s_dispatched = 0;

void isr_register(uint32_t line, isr_handler_t handler) {
    if (line < VLAB_IRQ_COUNT) {
        s_vectors[line] = handler;
    }
}

int isr_dispatch(void) {
    int handled = 0;
    /* Bounded: one pass per line max, so a constantly re-raising source
     * cannot livelock the dispatcher. */
    for (unsigned i = 0; i < VLAB_IRQ_COUNT; i++) {
        uint32_t line = hal_read_reg(VLAB_INTC_ACK);
        if (line == VLAB_IRQ_NONE || line >= VLAB_IRQ_COUNT) break;
        isr_handler_t h = s_vectors[line];
        if (h) h(line);
        /* ACK moved PENDING->ACTIVE; this clears ACTIVE (two-step). */
        hal_write_reg(VLAB_INTC_CLEAR, line);
        s_dispatched++;
        handled++;
    }
    return handled;
}

uint32_t isr_dispatched_count(void) { return s_dispatched; }
