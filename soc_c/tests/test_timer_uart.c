/* TIMER + UART validation in C.
 * Ports validation/interrupts/test_timer.py + validation/boot/test_uart.py.
 */
#include <assert.h>
#include <stdio.h>

#include "soc.h"

int main(void) {
    soc_t s;
    soc_config_t cfg;
    uint32_t v = 0;

    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    soc_boot(&s, NULL, 0);

    /* UART disabled TX returns -1, counts stall. */
    assert(soc_write(&s, SOC_UART_BASE + 0x00, 0x41) == SOC_UART_ERR_DISABLED);

    /* Enable + loopback one byte. */
    assert(soc_write(&s, SOC_UART_BASE + 0x0C, 0x1) == SOC_OK);
    assert(soc_write(&s, SOC_UART_BASE + 0x00, 0x41) == SOC_OK);
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && (v & 0x1));
    soc_step(&s, cfg.uart_latency_ticks);
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && (v & 0x4));
    assert(soc_read(&s, SOC_UART_BASE + 0x04, &v) == SOC_OK && v == 0x41);
    /* RX_VALID clears on read. */
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && !(v & 0x4));

    /* UART raises line 0 on completion when enabled. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SOC_UART_BASE + 0x0C, 0x1) == SOC_OK);
    assert(soc_write(&s, SOC_INTC_BASE + 0x00, 0x7) == SOC_OK);
    assert(soc_write(&s, SOC_UART_BASE + 0x00, 0x42) == SOC_OK);
    soc_step(&s, cfg.uart_latency_ticks);
    assert(soc_read(&s, SOC_INTC_BASE + 0x04, &v) == SOC_OK && (v & 0x1));
    assert(soc_read(&s, SOC_INTC_BASE + 0x08, &v) == SOC_OK && v == 0);

    /* TIMER one-shot fires once. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SOC_TIMER_BASE + 0x04, 10) == SOC_OK); /* LOAD */
    assert(soc_write(&s, SOC_TIMER_BASE + 0x00, 0x1 | 0x4) == SOC_OK); /* EN|IRQ */
    soc_step(&s, 10);
    assert(soc_read(&s, SOC_TIMER_BASE + 0x0C, &v) == SOC_OK && (v & 0x1));
    /* W1C clears. */
    assert(soc_write(&s, SOC_TIMER_BASE + 0x10, 0x1) == SOC_OK);
    assert(soc_read(&s, SOC_TIMER_BASE + 0x0C, &v) == SOC_OK && !(v & 0x1));

    /* TIMER periodic reloads. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SOC_TIMER_BASE + 0x04, 5) == SOC_OK);
    assert(soc_write(&s, SOC_TIMER_BASE + 0x00, 0x1 | 0x2 | 0x4) == SOC_OK);
    soc_step(&s, 5);
    assert(soc_read(&s, SOC_TIMER_BASE + 0x0C, &v) == SOC_OK && (v & 0x1));
    assert(soc_write(&s, SOC_TIMER_BASE + 0x10, 0x1) == SOC_OK);
    soc_step(&s, 5);
    assert(soc_read(&s, SOC_TIMER_BASE + 0x0C, &v) == SOC_OK && (v & 0x1));

    /* LOAD=0 + ENABLE never fires. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SOC_TIMER_BASE + 0x04, 0) == SOC_OK);
    assert(soc_write(&s, SOC_TIMER_BASE + 0x00, 0x1 | 0x4) == SOC_OK);
    soc_step(&s, 20);
    assert(soc_read(&s, SOC_TIMER_BASE + 0x0C, &v) == SOC_OK && !(v & 0x1));

    printf("TIMER_UART OK\n");
    return 0;
}
