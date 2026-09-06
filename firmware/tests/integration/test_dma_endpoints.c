/* DMA endpoint matrix + lifecycle on the live model.
 *
 * Proves the driver represents RAM->RAM, RAM->Peripheral and
 * Peripheral->RAM through platform caps + the DMA-capable FIFO table,
 * and that INVALID ADDRESS (unmapped) is distinct from VALID ADDRESS
 * BUT UNSUPPORTED DMA CAPABILITY (incapable endpoint, wrong role,
 * disallowed direction, over max). Every transfer runs on the ticking
 * engine (stepped to DONE); configuration persists across transfers.
 */
#include <assert.h>
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "host_bridge.h"
#include "isr.h"
#include "soc_regs.h"

#define SRAM_BASE 0x10000000U

/* Fresh model + VLAB platform config. The live SoC is global, so every
 * case starts here; driver lifecycle state must be IDLE (recover at the
 * end of any case that submits). */
static void t_boot(void) {
    soc_host_boot();
    dma_init();
}

static void clear_dma(void) { hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U); }

/* Step a started transfer to its terminal flag, then clear it. */
static void run_to_idle(void) {
    vlab_test_dma_complete();
    clear_dma();
}

static void test_valid_directions(void) {
    t_boot();
    /* RAM -> RAM (existing behavior, preserved). */
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 0) == VLAB_DMA_OK);
    run_to_idle();
    /* RAM -> Peripheral (uart-tx FIFO sink). */
    assert(dma_start(SRAM_BASE, VLAB_UART_TXDATA, 64, 0) == VLAB_DMA_OK);
    run_to_idle();
    /* Peripheral -> RAM (uart-rx FIFO source). */
    assert(dma_start(VLAB_UART_RXDATA, SRAM_BASE + 0x2000U, 64, 0) ==
           VLAB_DMA_OK);
    run_to_idle();
}

static void test_addr_vs_unsupported(void) {
    t_boot();
    /* Unmapped either side: INVALID ADDRESS. */
    assert(dma_start(0x30000000U, SRAM_BASE, 64, 0) == VLAB_DMA_ERR_ADDR);
    assert(dma_start(SRAM_BASE, 0x30000000U, 64, 0) == VLAB_DMA_ERR_ADDR);
    /* Overflowing range: likewise ADDR, not UNSUPPORTED. */
    assert(dma_start(0xFFFFFFFCU, SRAM_BASE, 64, 0) == VLAB_DMA_ERR_ADDR);
    /* Mapped MMIO with no capable FIFO (TIMER/DMA/INTC/PERF regs):
     * VALID ADDRESS BUT UNSUPPORTED DMA CAPABILITY. */
    assert(dma_start(SRAM_BASE, VLAB_TIMER_BASE, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(VLAB_TIMER_CTRL, SRAM_BASE, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(SRAM_BASE, VLAB_DMA_BASE, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(SRAM_BASE, VLAB_INTC_BASE, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(SRAM_BASE, VLAB_PERF_BASE, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
}

static void test_roles_and_directions(void) {
    t_boot();
    /* Capable FIFO, wrong role: uart-rx is source-only, uart-tx sink-only. */
    assert(dma_start(SRAM_BASE, VLAB_UART_RXDATA, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(VLAB_UART_TXDATA, SRAM_BASE, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    /* Capable FIFOs, disallowed direction: PERIPH -> PERIPH is in no
     * VLAB-supported direction set. */
    assert(dma_start(VLAB_UART_RXDATA, VLAB_UART_TXDATA, 64, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED);
    /* Same endpoints with the direction disabled via custom caps. */
    {
        static const struct dma_caps no_m2p = {4U, 16384U, true, false,
                                               true, true, false};
        dma_configure(NULL, 0, &no_m2p);
        assert(dma_start(SRAM_BASE, VLAB_UART_TXDATA, 64, 0) ==
               VLAB_DMA_ERR_UNSUPPORTED);
        assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 0) ==
               VLAB_DMA_OK);
        run_to_idle();
        dma_init(); /* restore VLAB defaults (map+caps+periph table) */
    }
}

static void test_invalid_use_codes(void) {
    t_boot();
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 0, 0) ==
           VLAB_DMA_ERR_LEN);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 6, 0) ==
           VLAB_DMA_ERR_LEN);
    assert(dma_start(SRAM_BASE + 1U, SRAM_BASE, 64, 0) ==
           VLAB_DMA_ERR_ALIGN);
    assert(dma_start(SRAM_BASE, VLAB_UART_TXDATA + 1U, 64, 0) ==
           VLAB_DMA_ERR_ALIGN);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 32768, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED); /* over 16KB max */
}

static void test_busy_and_lifecycle_on_peripheral(void) {
    uint32_t base;
    t_boot();
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
    base = dma_irq_count();
    /* START a peripheral transfer; second START while BUSY is refused. */
    assert(dma_start(SRAM_BASE, VLAB_UART_TXDATA, 64, 1) == VLAB_DMA_OK);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) ==
           VLAB_DMA_ERR_BUSY);
    /* Interrupt completion path works for the new direction. */
    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_COMPLETE);
    assert(dma_is_complete());
    assert(dma_irq_count() == base + 1U);
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    clear_dma();
    intc_enable(0U);
    isr_register(VLAB_IRQ_DMA, 0);
}

static void test_submit_recover_on_peripheral(void) {
    t_boot();
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
    /* Error completion + recovery on a peripheral transfer. */
    assert(dma_submit(VLAB_UART_RXDATA, SRAM_BASE + 0x3000U, 64, 1) ==
           VLAB_DMA_OK);
    vlab_test_dma_error(2U);
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_ERROR);
    assert(dma_latched_error() == 2U);
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    /* Configuration persists: no re-init needed between transfers. */
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x2000U, 64, 1) == VLAB_DMA_OK);
    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_COMPLETE);
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    intc_enable(0U);
    isr_register(VLAB_IRQ_DMA, 0);
}

int main(void) {
    test_valid_directions();
    test_addr_vs_unsupported();
    test_roles_and_directions();
    test_invalid_use_codes();
    test_busy_and_lifecycle_on_peripheral();
    test_submit_recover_on_peripheral();
    dma_init(); /* leave VLAB defaults installed for later suites */
    printf("test_dma_endpoints: all cases passed\n");
    return 0;
}
