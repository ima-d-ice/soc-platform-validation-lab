/* Fault behavior: stuck engines, synchronous errors, clean SRAM.
 *
 * No framework here on purpose: faults are latched directly in the
 * peripheral models (fault_stuck_busy flags), budgets are plain step
 * counts, and recovery is the existing two-step clear. Observable
 * behavior is what the test pins.
 */
#include <assert.h>
#include <stdio.h>

#include "soc.h"

#define DMA_STATUS (SOC_DMA_BASE + 0x10)
#define DMA_CTRL (SOC_DMA_BASE + 0x0C)
#define DONE (1U << 1)
#define ERROR (1U << 2)

int main(void) {
    soc_t s;
    soc_config_t cfg;
    uint32_t v = 0;

    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    soc_boot(&s, NULL, 0);

    /* Latching dma-timeout freezes countdown (stays BUSY). */
    assert(soc_write(&s, SOC_DMA_BASE + 0x00, SOC_SRAM_BASE) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x04, SOC_SRAM_BASE + 0x2000) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x08, 64) == SOC_OK);
    assert(soc_write(&s, DMA_CTRL, 0x1) == SOC_OK);
    s.dma.fault_stuck_busy = 1;
    soc_step(&s, 50);
    assert(soc_read(&s, DMA_STATUS, &v) == SOC_OK && (v & 0x1));
    s.dma.fault_stuck_busy = 0;
    soc_step(&s, 100);
    assert(soc_read(&s, DMA_STATUS, &v) == SOC_OK && (v & DONE));

    /* uart-stuck-busy freezes UART. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SOC_UART_BASE + 0x0C, 0x1) == SOC_OK);
    assert(soc_write(&s, SOC_UART_BASE + 0x00, 0x41) == SOC_OK);
    s.uart.fault_stuck_busy = 1;
    soc_step(&s, 20);
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && (v & 0x1));
    s.uart.fault_stuck_busy = 0;
    soc_step(&s, 10);
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && (v & 0x4));

    /* Invalid DMA fails synchronously with zero corruption. */
    soc_boot(&s, NULL, 0);
    assert(soc_sram_write_word(&s, SOC_SRAM_BASE + 0x3000, 0x12345678U) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x00, 0x30000000U) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x04, SOC_SRAM_BASE + 0x3000) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x08, 16) == SOC_OK);
    assert(soc_write(&s, DMA_CTRL, 0x1) == SOC_OK);
    soc_step(&s, 2);
    assert(soc_read(&s, DMA_STATUS, &v) == SOC_OK && (v & ERROR));
    assert(soc_sram_read_word(&s, SOC_SRAM_BASE + 0x3000, &v) == SOC_OK &&
           v == 0x12345678U);

    (void)v;
    printf("FAULTS OK\n");
    return 0;
}
