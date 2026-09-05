/* Countdown timer: one-shot / periodic + IRQ.
 * Mirrors soc/peripherals/timer/__init__.py.
 */
#ifndef SOC_C_TIMER_H
#define SOC_C_TIMER_H

#include <stdint.h>

#include "soc_bus.h"

#define SOC_TIMER_CTRL_OFF 0x00
#define SOC_TIMER_LOAD_OFF 0x04
#define SOC_TIMER_VALUE_OFF 0x08
#define SOC_TIMER_IRQ_STATUS_OFF 0x0C
#define SOC_TIMER_IRQ_CLEAR_OFF 0x10

#define SOC_TIMER_CTRL_ENABLE (1U << 0)
#define SOC_TIMER_CTRL_PERIODIC (1U << 1)
#define SOC_TIMER_CTRL_IRQ_ENABLE (1U << 2)
#define SOC_TIMER_IRQ_FIRED (1U << 0)

#define SOC_TIMER_IRQ_LINE 1

struct soc_intc_t;

typedef struct soc_timer_t {
    struct soc_intc_t *intc;
    uint32_t ctrl;
    uint32_t load;
    uint32_t value;
    uint32_t irq_status;
} soc_timer_t;

void soc_timer_init(soc_timer_t *t, struct soc_intc_t *intc);
void soc_timer_reset(soc_timer_t *t);
int soc_timer_read(soc_timer_t *t, uint32_t offset, uint32_t *out);
int soc_timer_write(soc_timer_t *t, uint32_t offset, uint32_t value);
void soc_timer_step(soc_timer_t *t);

#endif /* SOC_C_TIMER_H */
