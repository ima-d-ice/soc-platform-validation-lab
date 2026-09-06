/* VLAB platform bring-up: Reset -> startup (.data, .bss) -> ready.
 *
 * Host-native simulation of the copy/zero steps so the sequencing is real
 * code, not comments. The contract (disable IRQs, init PERF, init UART,
 * install DMA platform config) executes through HAL like any driver would.
 * Kept apart from platform_vlab.c (pure data, linked into the model
 * library) so static linking stays acyclic: firmware -> model, never back.
 */
#include "driver_api.h"
#include "hal.h"
#include "soc_regs.h"

/* Simulated image markers: .data source in "ROM", .data dest + .bss in RAM. */
static const uint32_t s_rom_data_init[4] = {0x11111111U, 0x22222222U, 0x33333333U,
                                            0x44444444U};
static uint32_t s_ram_data[4];
static uint32_t s_ram_bss[8];

int platform_init(void) {
    unsigned i;
    /* 1. Disable all IRQs during early init. */
    hal_write_reg(VLAB_INTC_ENABLE, 0U);
    /* 2. Reset + enable performance counters. */
    hal_write_reg(VLAB_PERF_CTRL, VLAB_PERF_CTRL_RESET);
    hal_write_reg(VLAB_PERF_CTRL, VLAB_PERF_CTRL_ENABLE);
    /* 3. .data copy (ROM -> RAM). */
    for (i = 0; i < 4; i++) s_ram_data[i] = s_rom_data_init[i];
    /* 4. .bss zero. */
    for (i = 0; i < 8; i++) s_ram_bss[i] = 0U;
    /* 5. Minimal UART init (bauddiv informational). */
    uart_init(0U);
    /* 6. DMA platform configuration (VLAB defaults; dma_configure can
     * override for another platform before first use). */
    dma_init();
    return 0;
}

/* Verify the .data/.bss contract held (host smoke test). */
int platform_self_check(void) {
    unsigned i;
    for (i = 0; i < 4; i++)
        if (s_ram_data[i] != s_rom_data_init[i]) return -1;
    for (i = 0; i < 8; i++)
        if (s_ram_bss[i] != 0U) return -2;
    return 0;
}
