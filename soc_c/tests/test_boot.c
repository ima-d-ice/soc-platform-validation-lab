/* Boot validation in C: reset -> ROM -> startup -> main.
 * Ports validation/boot/test_boot.py.
 */
#include <assert.h>
#include <stdio.h>

#include "soc.h"

int main(void) {
    soc_t s;
    soc_config_t cfg;
    soc_boot_info_t info;
    uint32_t rom_words[2] = {0x12345678U, 0x9ABCDEF0U};
    uint32_t v = 0;

    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    info = soc_boot(&s, rom_words, 2);
    assert(s.cpu.running == 1);
    assert(s.cpu.pc == SOC_ROM_BASE);
    assert(s.cpu.sp == SOC_SRAM_BASE + s.regions[1].size); /* SP = SRAM top */
    assert(info.boot_ticks == SOC_BOOT_TICKS && info.boot_ticks == 5);
    assert(s.ticks == SOC_BOOT_TICKS);
    assert(soc_read(&s, SOC_ROM_BASE, &v) == SOC_OK && v == 0x12345678U);
    assert(s.perf.enabled == 1);
    assert(s.perf.cycles == SOC_BOOT_TICKS);

    /* BSS zeroed, dirty then reboot zeroes again. */
    assert(soc_sram_read_word(&s, SOC_SRAM_BASE, &v) == SOC_OK && v == 0);
    assert(soc_sram_write_word(&s, SOC_SRAM_BASE, 0xDEADBEEFU) == SOC_OK);
    assert(soc_sram_read_word(&s, SOC_SRAM_BASE, &v) == SOC_OK &&
           v == 0xDEADBEEFU);
    soc_boot(&s, NULL, 0);
    assert(soc_sram_read_word(&s, SOC_SRAM_BASE, &v) == SOC_OK && v == 0);

    /* Determinism + boot_ns derivation. */
    {
        soc_boot_info_t a = soc_boot(&s, NULL, 0);
        soc_boot_info_t b = soc_boot(&s, NULL, 0);
        assert(a.boot_ticks == b.boot_ticks);
        assert(a.boot_ns == a.boot_ticks * 1000 / cfg.cpu_frequency_mhz);
    }
    printf("BOOT OK ticks=%u ns=%u\n", info.boot_ticks, info.boot_ns);
    return 0;
}
