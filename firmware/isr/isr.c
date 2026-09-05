/* ISR dispatch implementation. See include/isr.h for the contract.
 *
 * The dispatcher is generic over the platform's line count: vectors are
 * statically allocated up to ISR_MAX_LINES (no heap in firmware), and
 * isr_configure() installs how many lines the platform actually has.
 * IRQ *numbers* come from the platform register spec (soc_regs.h), never
 * from this file. Default configuration is the VLAB 3-line map.
 */
#include "isr.h"

#include "driver_api.h"
#include "hal.h"
#include "soc_regs.h"

static isr_handler_t s_vectors[ISR_MAX_LINES] = {0};
static uint32_t s_n_lines = VLAB_IRQ_COUNT;
static volatile uint32_t s_dispatched = 0;

void isr_configure(uint32_t n_lines) {
    uint32_t i;
    if (n_lines == 0 || n_lines > ISR_MAX_LINES) return; /* keep old config */
    s_n_lines = n_lines;
    for (i = 0; i < ISR_MAX_LINES; i++) s_vectors[i] = 0;
}

void isr_register(uint32_t line, isr_handler_t handler) {
    if (line < s_n_lines) {
        s_vectors[line] = handler;
    }
}

int isr_dispatch(void) {
    int handled = 0;
    uint32_t i;
    /* Bounded: one pass per configured line max, so a constantly
     * re-raising source cannot livelock the dispatcher. */
    for (i = 0; i < s_n_lines; i++) {
        uint32_t line = hal_read_reg(VLAB_INTC_ACK);
        if (line == VLAB_IRQ_NONE || line >= s_n_lines) break;
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
