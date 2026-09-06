/* Bus + decode validation: faults, region map, and boundaries. */
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

    /* Platform map: 7 regions at the spec bases. */
    assert(s.n_regions == 7);
    assert(s.regions[0].base == SOC_ROM_BASE);
    assert(s.regions[1].base == SOC_SRAM_BASE);
    assert(s.regions[2].base == SOC_UART_BASE);
    assert(s.regions[3].base == SOC_TIMER_BASE);
    assert(s.regions[4].base == SOC_DMA_BASE);
    assert(s.regions[5].base == SOC_INTC_BASE);
    assert(s.regions[6].base == SOC_PERF_BASE);
    /* SRAM boundaries: last word ok, one past faults. */
    assert(soc_write(&s, SOC_SRAM_BASE, 0xA5A5A5A5U) == SOC_OK);
    assert(soc_read(&s, SOC_SRAM_BASE, &v) == SOC_OK && v == 0xA5A5A5A5U);
    assert(soc_write(&s, SOC_SRAM_BASE + s.regions[1].size - 4, 1) == SOC_OK);
    assert(soc_read(&s, SOC_SRAM_BASE + s.regions[1].size, &v) == SOC_ERR_BUS);
    /* MMIO edges: TIMER base decodes to timer, past PERF faults. */
    assert(soc_read(&s, SOC_TIMER_BASE, &v) == SOC_OK);
    assert(soc_read(&s, SOC_PERF_BASE + 0x1000, &v) == SOC_ERR_BUS);

    /* Unaligned access faults. */
    assert(soc_read(&s, SOC_SRAM_BASE + 1, &v) == SOC_ERR_BUS);
    assert(soc_write(&s, SOC_SRAM_BASE + 1, 0x1234) == SOC_ERR_BUS);
    /* Unmapped address faults. */
    assert(soc_read(&s, 0x30000000U, &v) == SOC_ERR_BUS);
    assert(soc_write(&s, 0x30000000U, 1) == SOC_ERR_BUS);
    /* ROM write faults at run time. */
    assert(soc_write(&s, SOC_ROM_BASE, 0xDEADU) == SOC_ERR_BUS);
    /* UART WO/RO violations. */
    assert(soc_read(&s, SOC_UART_BASE + 0x00, &v) == SOC_ERR_BUS); /* TXDATA WO */
    assert(soc_write(&s, SOC_UART_BASE + 0x04, 1) == SOC_ERR_BUS); /* RXDATA RO */
    assert(soc_write(&s, SOC_UART_BASE + 0x08, 1) == SOC_ERR_BUS); /* STATUS RO */
    /* TIMER WO/RO violations. */
    assert(soc_read(&s, SOC_TIMER_BASE + 0x10, &v) == SOC_ERR_BUS);
    assert(soc_write(&s, SOC_TIMER_BASE + 0x08, 1) == SOC_ERR_BUS);
    /* DMA WO/RO violations. */
    assert(soc_read(&s, SOC_DMA_BASE + 0x14, &v) == SOC_ERR_BUS);
    assert(soc_write(&s, SOC_DMA_BASE + 0x10, 1) == SOC_ERR_BUS);
    assert(soc_write(&s, SOC_DMA_BASE + 0x18, 1) == SOC_ERR_BUS);
    /* INTC RO violations. */
    assert(soc_write(&s, SOC_INTC_BASE + 0x04, 1) == SOC_ERR_BUS);
    assert(soc_write(&s, SOC_INTC_BASE + 0x08, 1) == SOC_ERR_BUS);
    assert(soc_write(&s, SOC_INTC_BASE + 0x10, 1) == SOC_ERR_BUS);
    /* Stalls counted on faults. */
    assert(s.perf.stalls > 0);

    printf("BUS_ERRORS OK stalls=%u\n", s.perf.stalls);
    return 0;
}
