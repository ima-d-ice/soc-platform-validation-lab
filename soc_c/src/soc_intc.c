#include "soc.h"

static const int kPriority[3] = {SOC_IRQ_TIMER, SOC_IRQ_DMA, SOC_IRQ_UART};

void soc_intc_init(soc_intc_t *ic, struct soc_perf_t *perf) {
    ic->enable = 0;
    ic->pending = 0;
    ic->active = 0;
    ic->perf = perf;
}

void soc_intc_reset(soc_intc_t *ic) {
    ic->enable = 0;
    ic->pending = 0;
    ic->active = 0;
}

void soc_intc_raise(soc_intc_t *ic, int line) {
    if (line >= 0 && line < SOC_N_LINES) ic->pending |= (1U << line);
}

static int soc_intc_highest(soc_intc_t *ic) {
    uint32_t gated = ic->pending & ic->enable & 0x7U;
    int i;
    for (i = 0; i < 3; i++) {
        if (gated & (1U << kPriority[i])) return kPriority[i];
    }
    return -1;
}

int soc_intc_read(soc_intc_t *ic, uint32_t offset, uint32_t *out) {
    int line;
    switch (offset) {
        case SOC_INTC_ENABLE_OFF: *out = ic->enable; return SOC_OK;
        case SOC_INTC_PENDING_OFF: *out = ic->pending; return SOC_OK;
        case SOC_INTC_ACTIVE_OFF: *out = ic->active; return SOC_OK;
        case SOC_INTC_ACK_OFF:
            line = soc_intc_highest(ic);
            if (line < 0) {
                *out = SOC_IRQ_NONE;
                return SOC_OK;
            }
            ic->pending &= ~(1U << line);
            ic->active |= (1U << line);
            if (ic->perf) soc_perf_count_irq(ic->perf);
            *out = (uint32_t)line;
            return SOC_OK;
        default: return SOC_ERR_BUS;
    }
}

int soc_intc_write(soc_intc_t *ic, uint32_t offset, uint32_t value) {
    switch (offset) {
        case SOC_INTC_ENABLE_OFF: ic->enable = value & 0x7U; return SOC_OK;
        case SOC_INTC_CLEAR_OFF:
            if (value < (uint32_t)SOC_N_LINES)
                ic->active &= ~(1U << value);
            return SOC_OK;
        case SOC_INTC_PENDING_OFF:
        case SOC_INTC_ACK_OFF:
        case SOC_INTC_ACTIVE_OFF:
            return SOC_ERR_BUS;
        default: return SOC_ERR_BUS;
    }
}
