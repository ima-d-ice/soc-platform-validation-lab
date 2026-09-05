/* Integration: default VLAB platform wiring end to end.
 *
 * Proves dma_init() installs a working configuration: submit a transfer,
 * complete it through isr_dispatch(), verify flags/state/counters, and
 * recover to IDLE. Uses the host engine stand-ins (test hooks) for the
 * completion event itself.
 */
#include <assert.h>
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "isr.h"
#include "soc_regs.h"

#define SRAM_BASE 0x10000000U

static void test_vlab_default_cycle(void) {
    dma_init();
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);

    assert(dma_state() == DMA_S_IDLE);
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 256, 1) == VLAB_DMA_OK);
    assert(dma_state() == DMA_S_ACTIVE);
    assert(!dma_is_complete());

    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    assert(dma_is_complete());
    assert(dma_state() == DMA_S_COMPLETE);
    assert(dma_irq_count() == 1U);

    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    assert(!dma_is_complete());
    intc_enable(0U);
    isr_register(VLAB_IRQ_DMA, 0);
}

static void test_second_cycle_reuses_config(void) {
    /* Configuration persists: no re-init needed between transfers. */
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x2000U, 64, 1) == VLAB_DMA_OK);
    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_COMPLETE);
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    assert(dma_irq_count() == 2U); /* one per cycle, cumulative */
    intc_enable(0U);
    isr_register(VLAB_IRQ_DMA, 0);
}

int main(void) {
    test_vlab_default_cycle();
    test_second_cycle_reuses_config();
    printf("test_dma_platform: all cases passed\n");
    return 0;
}
