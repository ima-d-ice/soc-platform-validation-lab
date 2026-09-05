/* INTC + priority validation in C.
 * Ports validation/interrupts/test_intc.py + test_priority.py.
 */
#include <assert.h>
#include <stdio.h>

#include "soc.h"

#define INTC_ENABLE (SOC_INTC_BASE + 0x00)
#define INTC_PENDING (SOC_INTC_BASE + 0x04)
#define INTC_ACK (SOC_INTC_BASE + 0x08)
#define INTC_CLEAR (SOC_INTC_BASE + 0x0C)
#define INTC_ACTIVE (SOC_INTC_BASE + 0x10)

int main(void) {
    soc_t s;
    soc_config_t cfg;
    uint32_t v = 0;

    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    soc_boot(&s, NULL, 0);

    /* Spurious ACK returns NONE, counts nothing. */
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == 0xFFFFFFFFU);
    assert(s.perf.irq_count == 0);

    /* Enable gates ACK only; pending records while disabled. */
    soc_intc_raise(&s.intc, SOC_IRQ_TIMER);
    assert(soc_read(&s, INTC_PENDING, &v) == SOC_OK && (v & (1U << 1)));
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == 0xFFFFFFFFU);
    assert(soc_write(&s, INTC_ENABLE, 0x7) == SOC_OK);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == SOC_IRQ_TIMER);
    assert(soc_read(&s, INTC_ACTIVE, &v) == SOC_OK && (v & (1U << 1)));
    assert(soc_write(&s, INTC_CLEAR, SOC_IRQ_TIMER) == SOC_OK);
    assert(soc_read(&s, INTC_ACTIVE, &v) == SOC_OK && !(v & (1U << 1)));

    /* Priority: TIMER(1) > DMA(2) > UART(0). */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, INTC_ENABLE, 0x7) == SOC_OK);
    soc_intc_raise(&s.intc, SOC_IRQ_UART);
    soc_intc_raise(&s.intc, SOC_IRQ_DMA);
    soc_intc_raise(&s.intc, SOC_IRQ_TIMER);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == SOC_IRQ_TIMER);
    assert(soc_write(&s, INTC_CLEAR, SOC_IRQ_TIMER) == SOC_OK);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == SOC_IRQ_DMA);
    assert(soc_write(&s, INTC_CLEAR, SOC_IRQ_DMA) == SOC_OK);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == SOC_IRQ_UART);
    assert(soc_write(&s, INTC_CLEAR, SOC_IRQ_UART) == SOC_OK);

    /* Coalesce: N raises before ACK yield one pending + one ACK. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, INTC_ENABLE, 0x7) == SOC_OK);
    soc_intc_raise(&s.intc, SOC_IRQ_TIMER);
    soc_intc_raise(&s.intc, SOC_IRQ_TIMER);
    soc_intc_raise(&s.intc, SOC_IRQ_TIMER);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == SOC_IRQ_TIMER);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == 0xFFFFFFFFU);

    /* CLEAR out-of-range ignored, no fault. */
    assert(soc_write(&s, INTC_CLEAR, 99) == SOC_OK);
    /* Double-ACK returns NONE. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, INTC_ENABLE, 0x7) == SOC_OK);
    soc_intc_raise(&s.intc, SOC_IRQ_DMA);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == SOC_IRQ_DMA);
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == 0xFFFFFFFFU);

    printf("INTC OK irqs=%u\n", s.perf.irq_count);
    return 0;
}
