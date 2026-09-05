/* Memory region validation in C. Ports validation/memory/test_regions.py. */
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

    /* 7 regions, correct bases. */
    assert(s.regions[0].base == SOC_ROM_BASE);
    assert(s.regions[1].base == SOC_SRAM_BASE);
    assert(s.regions[2].base == SOC_UART_BASE);
    assert(s.regions[3].base == SOC_TIMER_BASE);
    assert(s.regions[4].base == SOC_DMA_BASE);
    assert(s.regions[5].base == SOC_INTC_BASE);
    assert(s.regions[6].base == SOC_PERF_BASE);
    assert(s.regions[1].size == cfg.sram_size_bytes);

    /* ROM readable, SRAM rw, boundary checks. */
    assert(soc_write(&s, SOC_SRAM_BASE, 0xA5A5A5A5U) == SOC_OK);
    assert(soc_read(&s, SOC_SRAM_BASE, &v) == SOC_OK && v == 0xA5A5A5A5U);
    /* Last word of SRAM ok, one past faults. */
    assert(soc_write(&s, SOC_SRAM_BASE + cfg.sram_size_bytes - 4, 1) == SOC_OK);
    assert(soc_read(&s, SOC_SRAM_BASE + cfg.sram_size_bytes, &v) == SOC_ERR_BUS);
    /* MMIO window edges: UART ctrl ok, invalid UART offset faults,
     * TIMER base decodes to timer, past PERF faults. */
    assert(soc_write(&s, SOC_UART_BASE + 0x0C, 1) == SOC_OK);
    assert(soc_read(&s, SOC_UART_BASE + 0xFFC, &v) == SOC_ERR_BUS);
    assert(soc_read(&s, SOC_TIMER_BASE, &v) == SOC_OK);
    assert(soc_read(&s, SOC_PERF_BASE + 0x1000, &v) == SOC_ERR_BUS);

    printf("REGIONS OK\n");
    return 0;
}
