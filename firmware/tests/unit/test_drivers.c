/* Driver unit tests: validation ordering, error codes, register effects.
 *
 * Runs against the live model: every case boots it first (global SoC, so
 * state never leaks between cases), and every started transfer is stepped
 * to DONE because the engine stays BUSY until time passes.
 */
#include <assert.h>
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "host_bridge.h"
#include "soc_regs.h"

#define SRAM_BASE 0x10000000U

/* Fresh model + VLAB platform config; engine idle. */
static void t_boot(void) {
    soc_host_boot();
    dma_init();
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
}

static void test_dma_validation_order(void) {
    t_boot();
    /* LEN checked before ALIGN before ADDR. */
    assert(dma_start(0x30000001U, SRAM_BASE, 0, 0) == VLAB_DMA_ERR_LEN);
    assert(dma_start(SRAM_BASE + 1U, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ALIGN);
    assert(dma_start(0x30000000U, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ADDR);
    assert(dma_start(SRAM_BASE, 0x40000000U, 16, 0) == VLAB_DMA_ERR_ADDR);
}

static void test_dma_programs_registers(void) {
    t_boot();
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    assert(hal_read_reg(VLAB_DMA_SRC) == SRAM_BASE);
    assert(hal_read_reg(VLAB_DMA_DST) == SRAM_BASE + 0x1000U);
    assert(hal_read_reg(VLAB_DMA_LEN) == 64U);
    /* START self-clears; IRQ_EN latched; engine BUSY until stepped. */
    assert(hal_read_reg(VLAB_DMA_CTRL) == VLAB_DMA_CTRL_IRQ_ENABLE);
    assert(hal_read_reg(VLAB_DMA_STATUS) & VLAB_DMA_STATUS_BUSY);
    vlab_test_dma_complete(); /* step the live engine to DONE */
    assert(hal_read_reg(VLAB_DMA_STATUS) & VLAB_DMA_STATUS_DONE);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
}

static void test_uart_disabled_rejected(void) {
    uint8_t b = 0;
    t_boot();
    hal_write_reg(VLAB_UART_CTRL, 0U); /* ensure disabled */
    assert(uart_write_byte(0x41U) == VLAB_UART_ERR_DISABLED);
    assert(uart_init(0U) == VLAB_UART_OK);
    assert(uart_write_byte(0x41U) == VLAB_UART_OK);
    /* Loopback needs latency ticks; too early is a timeout, not data. */
    assert(uart_read_byte(&b) == VLAB_UART_ERR_TIMEOUT);
    soc_host_step(5);
    assert(uart_read_byte(&b) == VLAB_UART_OK);
    assert(b == 0x41U);
}

static void test_timer_rejects_zero_load(void) {
    t_boot();
    assert(timer_start(0, 0, 0) == -1);
    assert(timer_start(100, 0, 1) == 0);
    assert(hal_read_reg(VLAB_TIMER_LOAD) == 100U);
    timer_stop();
    assert(hal_read_reg(VLAB_TIMER_CTRL) == 0U);
}

static void test_intc_mask_and_ack(void) {
    t_boot();
    intc_enable(0xFFU);
    assert(hal_read_reg(VLAB_INTC_ENABLE) == 0x7U); /* masked to 3 lines */
    assert(intc_ack() == 0xFFFFFFFFU); /* nothing pending on live model */
    intc_enable(0U);
    assert(hal_read_reg(VLAB_INTC_ENABLE) == 0U);
}

int main(void) {
    test_dma_validation_order();
    test_dma_programs_registers();
    test_uart_disabled_rejected();
    test_timer_rejects_zero_load();
    test_intc_mask_and_ack();
    printf("test_drivers: all cases passed\n");
    return 0;
}
