/* Fault tests: invalid use rejected pre-START, error latched via ISR,
 * recovery restores a working engine. Complements soc_c_faults
 * (model-level faults) at the C driver level.
 */
#include <assert.h>
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "isr.h"
#include "soc_regs.h"

#define SRAM_BASE 0x10000000U

static void setup(void) {
    dma_init();
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
}

static void teardown(void) {
    dma_recover();
    intc_enable(0U);
    isr_register(VLAB_IRQ_DMA, 0);
}

static void test_invalid_src_rejected_without_start(void) {
    setup();
    /* Unmapped source: invalid use -> ERR_ADDR, engine never STARTed. */
    assert(dma_submit(0x30000000U, SRAM_BASE, 64, 1) == VLAB_DMA_ERR_ADDR);
    assert(dma_state() == DMA_S_IDLE);
    assert(!(hal_read_reg(VLAB_DMA_STATUS) & VLAB_DMA_STATUS_BUSY));
    assert(hal_read_reg(VLAB_INTC_PENDING) == 0U); /* no spurious IRQ */
    teardown();
}

static void test_unsupported_platform_rejected(void) {
    setup();
    /* Mapped MMIO endpoint, VLAB caps forbid peripheral direction. */
    assert(dma_submit(SRAM_BASE, VLAB_UART_BASE, 64, 1) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_state() == DMA_S_IDLE);
    /* Over max transfer: likewise platform, not API. */
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 32768, 1) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_state() == DMA_S_IDLE);
    teardown();
}

static void test_error_latch_and_recovery(void) {
    setup();
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    vlab_test_dma_error(1U);
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_ERROR);
    assert(dma_latched_error() == 1U);
    assert(!dma_is_complete());
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    assert(dma_latched_error() == 0U);
    /* Engine healthy again. */
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_COMPLETE);
    teardown();
}

int main(void) {
    test_invalid_src_rejected_without_start();
    test_unsupported_platform_rejected();
    test_error_latch_and_recovery();
    printf("test_dma_faults: all cases passed\n");
    return 0;
}
