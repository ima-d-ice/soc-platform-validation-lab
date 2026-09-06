/* Firmware+model link test: real C drivers on the real C SoC model.
 * Links firmware/drivers/uart/uart.c + hal/hal.c + hal/host.c against
 * soc_c + host_bridge (no mmio.c shim). Proves unification: driver
 * register traffic drives modeled timing + IRQs.
 */
#include <assert.h>
#include <stdio.h>

#include "driver_api.h"
#include "host_bridge.h"
#include "soc.h"
#include "soc_regs.h"

int main(void) {
    soc_config_t cfg;
    uint8_t b = 0;
    uint32_t pending = 0;

    soc_config_default(&cfg);
    soc_host_init(&cfg);
    soc_host_boot();
    dma_init();

    /* UART via driver, timing via model. */
    assert(uart_init(0) == VLAB_UART_OK);
    assert(uart_write_byte(0x41) == VLAB_UART_OK);
    /* Not yet looped back (busy latency). */
    assert(uart_read_byte(&b) == VLAB_UART_ERR_TIMEOUT);
    soc_host_step(cfg.uart_latency_ticks);
    assert(uart_read_byte(&b) == VLAB_UART_OK && b == 0x41);

    /* DMA via driver MMIO, completion via model stepping. */
    {
        soc_t *s = soc_host_soc();
        uint32_t i;
        for (i = 0; i < 16; i++)
            soc_sram_write_word(s, SOC_SRAM_BASE + i * 4,
                                0xA5000000U | i);
        assert(dma_start(SOC_SRAM_BASE, SOC_SRAM_BASE + 0x1000, 64, 0) ==
               VLAB_DMA_OK);
        soc_host_step(100);
        assert((dma_status() & VLAB_DMA_STATUS_DONE) ||
               (dma_status() & 0x2));
        for (i = 0; i < 16; i++) {
            uint32_t v = 0;
            soc_sram_read_word(s, SOC_SRAM_BASE + 0x1000 + i * 4, &v);
            assert(v == (0xA5000000U | i));
        }
        dma_clear();
    }

    /* DMA peripheral round-trip via driver API: RAM -> uart-tx, then
     * uart-rx -> RAM. Validates through the driver, moves through the
     * model FIFOs, byte-compares at the end. */
    {
        soc_t *s = soc_host_soc();
        uint32_t i;
        soc_host_boot();
        dma_init();
        for (i = 0; i < 16; i++)
            soc_sram_write_word(s, SOC_SRAM_BASE + 0x4000 + i * 4,
                                0xC3000000U | i);
        assert(dma_start(SOC_SRAM_BASE + 0x4000, VLAB_UART_TXDATA, 64, 0) ==
               VLAB_DMA_OK);
        soc_host_step(100);
        assert(dma_status() & VLAB_DMA_STATUS_DONE);
        dma_clear();
        assert(dma_start(VLAB_UART_RXDATA, SOC_SRAM_BASE + 0x5000, 64, 0) ==
               VLAB_DMA_OK);
        soc_host_step(100);
        assert(dma_status() & VLAB_DMA_STATUS_DONE);
        for (i = 0; i < 16; i++) {
            uint32_t v = 0;
            soc_sram_read_word(s, SOC_SRAM_BASE + 0x5000 + i * 4, &v);
            assert(v == (0xC3000000U | i));
        }
        dma_clear();
        /* Mapped-but-incapable peripheral stays UNSUPPORTED here too. */
        assert(dma_start(SOC_SRAM_BASE, VLAB_TIMER_BASE, 64, 0) ==
               VLAB_DMA_ERR_UNSUPPORTED);
    }

    /* IRQ path: UART completion raises line 0. */
    soc_host_boot();
    assert(uart_init(0) == VLAB_UART_OK);
    soc_write(soc_host_soc(), SOC_INTC_BASE, 0x7);
    assert(uart_write_byte(0x42) == VLAB_UART_OK);
    soc_host_step(cfg.uart_latency_ticks);
    soc_read(soc_host_soc(), SOC_INTC_BASE + 0x04, &pending);
    assert(pending & 0x1);

    printf("FIRMWARE_LINK OK\n");
    return 0;
}
