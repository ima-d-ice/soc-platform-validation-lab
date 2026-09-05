/* Fault injection + recovery in C. Ports validation/faults/. */
#include <assert.h>
#include <stdio.h>

#include "soc.h"
#include "soc_faults.h"

#define DMA_STATUS (SOC_DMA_BASE + 0x10)
#define DMA_CTRL (SOC_DMA_BASE + 0x0C)
#define DONE (1U << 1)
#define ERROR (1U << 2)

int main(void) {
    soc_t s;
    soc_config_t cfg;
    soc_fault_injector_t fi;
    soc_recovery_tracker_t tr;
    uint32_t v = 0;

    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    soc_boot(&s, NULL, 0);

    /* Latching dma-timeout freezes countdown (stays BUSY). */
    soc_fault_injector_init(&fi, &s);
    assert(soc_write(&s, SOC_DMA_BASE + 0x00, SOC_SRAM_BASE) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x04, SOC_SRAM_BASE + 0x2000) == SOC_OK);
    assert(soc_write(&s, SOC_DMA_BASE + 0x08, 64) == SOC_OK);
    assert(soc_write(&s, DMA_CTRL, 0x1) == SOC_OK);
    soc_fault_inject(&fi, "dma-timeout");
    assert(soc_fault_is_active(&fi, "dma-timeout"));
    soc_step(&s, 50);
    assert(soc_read(&s, DMA_STATUS, &v) == SOC_OK && (v & 0x1));
    soc_fault_clear(&fi, "dma-timeout");
    soc_step(&s, 100);
    assert(soc_read(&s, DMA_STATUS, &v) == SOC_OK && (v & DONE));

    /* uart-stuck-busy freezes UART. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SOC_UART_BASE + 0x0C, 0x1) == SOC_OK);
    assert(soc_write(&s, SOC_UART_BASE + 0x00, 0x41) == SOC_OK);
    soc_fault_inject(&fi, "uart-stuck-busy");
    soc_step(&s, 20);
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && (v & 0x1));
    soc_fault_clear(&fi, "uart-stuck-busy");
    soc_step(&s, 10);
    assert(soc_read(&s, SOC_UART_BASE + 0x08, &v) == SOC_OK && (v & 0x4));

    /* Recovery tracker legal path. */
    soc_recovery_init(&tr);
    assert(soc_recovery_on_fault(&tr, 10, "dma-timeout") == 0);
    assert(soc_recovery_on_detected(&tr, 12) == 0);
    assert(soc_recovery_on_recovery_start(&tr) == 0);
    assert(soc_recovery_on_recovered(&tr, 20) == 0);
    assert(tr.current == SOC_RS_RECOVERED);
    /* Illegal transition rejected. */
    soc_recovery_init(&tr);
    assert(soc_recovery_on_recovered(&tr, 5) != 0);

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
