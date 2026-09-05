#include "soc_timer.h"

#include "soc_intc.h"

void soc_timer_init(soc_timer_t *t, struct soc_intc_t *intc) {
    t->intc = intc;
    t->ctrl = 0;
    t->load = 0;
    t->value = 0;
    t->irq_status = 0;
}

void soc_timer_reset(soc_timer_t *t) {
    t->ctrl = 0;
    t->load = 0;
    t->value = 0;
    t->irq_status = 0;
}

int soc_timer_read(soc_timer_t *t, uint32_t offset, uint32_t *out) {
    switch (offset) {
        case SOC_TIMER_CTRL_OFF: *out = t->ctrl; return SOC_OK;
        case SOC_TIMER_LOAD_OFF: *out = t->load; return SOC_OK;
        case SOC_TIMER_VALUE_OFF: *out = t->value; return SOC_OK;
        case SOC_TIMER_IRQ_STATUS_OFF: *out = t->irq_status; return SOC_OK;
        case SOC_TIMER_IRQ_CLEAR_OFF: return SOC_ERR_BUS;
        default: return SOC_ERR_BUS;
    }
}

int soc_timer_write(soc_timer_t *t, uint32_t offset, uint32_t value) {
    int was_enabled, now_enabled;
    switch (offset) {
        case SOC_TIMER_CTRL_OFF:
            was_enabled = (t->ctrl & SOC_TIMER_CTRL_ENABLE) ? 1 : 0;
            t->ctrl = value;
            now_enabled = (t->ctrl & SOC_TIMER_CTRL_ENABLE) ? 1 : 0;
            if (now_enabled && !was_enabled && t->value == 0)
                t->value = t->load;
            return SOC_OK;
        case SOC_TIMER_LOAD_OFF: t->load = value; return SOC_OK;
        case SOC_TIMER_IRQ_STATUS_OFF:
            if (value & SOC_TIMER_IRQ_FIRED)
                t->irq_status &= ~SOC_TIMER_IRQ_FIRED;
            return SOC_OK;
        case SOC_TIMER_IRQ_CLEAR_OFF:
            if (value & SOC_TIMER_IRQ_FIRED)
                t->irq_status &= ~SOC_TIMER_IRQ_FIRED;
            return SOC_OK;
        case SOC_TIMER_VALUE_OFF:
            return SOC_ERR_BUS;
        default: return SOC_ERR_BUS;
    }
}

void soc_timer_step(soc_timer_t *t) {
    if (!(t->ctrl & SOC_TIMER_CTRL_ENABLE)) return;
    if (t->load == 0) return;
    if (t->value > 0) t->value--;
    if (t->value == 0) {
        t->irq_status |= SOC_TIMER_IRQ_FIRED;
        if ((t->ctrl & SOC_TIMER_CTRL_IRQ_ENABLE) && t->intc)
            soc_intc_raise(t->intc, SOC_TIMER_IRQ_LINE);
        if (t->ctrl & SOC_TIMER_CTRL_PERIODIC)
            t->value = t->load;
        else
            t->ctrl &= ~SOC_TIMER_CTRL_ENABLE;
    }
}
