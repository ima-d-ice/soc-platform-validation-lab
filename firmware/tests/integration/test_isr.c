/* ISR + DMA state-machine tests: dispatch, completion, error, recovery.
 *
 * The host has no preemptive IRQs, so tests raise engine/IRQ events via
 * the live-model hooks and then call isr_dispatch() exactly as a main
 * loop / tick hook would. Handler logic, flags, ordering, and lifecycle
 * are all real code under test. The model is global, so every case starts
 * from a fresh boot; every case also ends with lifecycle IDLE.
 */
#include <assert.h>
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "host_bridge.h"
#include "isr.h"
#include "soc_regs.h"

#define SRAM_BASE 0x10000000U

static void reset_all(void) {
    soc_host_boot(); /* engine idle, INTC/UART/PERF at reset values */
    dma_init();      /* VLAB platform defaults */
    intc_enable(0U);
    isr_configure(VLAB_IRQ_COUNT); /* platform default: 3 live lines */
    assert(dma_state() == DMA_S_IDLE); /* previous case ended IDLE */
}

static void test_dispatch_empty(void) {
    reset_all();
    assert(isr_dispatch() == 0);
}

static void test_completion_path(void) {
    reset_all();
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    assert(dma_state() == DMA_S_ACTIVE);
    assert(!dma_is_complete()); /* polled flag: no bus traffic */
    assert(hal_read_reg(VLAB_DMA_STATUS) & VLAB_DMA_STATUS_BUSY);
    vlab_test_dma_complete(); /* engine finishes (test hook) */
    assert(isr_dispatch() == 1);
    assert(dma_is_complete());
    assert(dma_state() == DMA_S_COMPLETE);
    assert(dma_irq_count() >= 1U);
    /* ISR performed the two-step clear: engine idle, INTC clean. */
    assert(hal_read_reg(VLAB_DMA_STATUS) == 0U);
    assert(hal_read_reg(VLAB_INTC_PENDING) == 0U);
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
}

static void test_error_path_and_recover(void) {
    reset_all();
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    vlab_test_dma_error(1U); /* invalid-address error (test hook) */
    assert(isr_dispatch() == 1);
    assert(!dma_is_complete());
    assert(dma_state() == DMA_S_ERROR);
    assert(dma_latched_error() == 1U);
    dma_recover();
    assert(dma_state() == DMA_S_IDLE);
    assert(dma_latched_error() == 0U);
    /* Engine healthy again: full cycle runs. */
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    assert(dma_state() == DMA_S_COMPLETE);
    dma_recover();
}

static void test_submit_lifecycle_guards(void) {
    reset_all();
    intc_enable(1U << VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, dma_isr);
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_OK);
    /* Second submit while ACTIVE is rejected without touching hardware. */
    assert(dma_submit(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 1) == VLAB_DMA_ERR_BUSY);
    /* Validation failures leave state IDLE (after recovery to IDLE). */
    vlab_test_dma_complete();
    assert(isr_dispatch() == 1);
    dma_recover();
    assert(dma_submit(0x30000000U, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ADDR);
    assert(dma_state() == DMA_S_IDLE);
}

static void test_unregistered_line_still_cleared(void) {
    reset_all();
    intc_enable(1U << VLAB_IRQ_TIMER);
    isr_register(VLAB_IRQ_TIMER, 0); /* no handler */
    vlab_test_raise_irq(VLAB_IRQ_TIMER);
    assert(isr_dispatch() == 1); /* ACKed + cleared, no wedge */
    assert(hal_read_reg(VLAB_INTC_PENDING) == 0U);
    assert(hal_read_reg(VLAB_INTC_ACTIVE) == 0U);
    intc_enable(0U);
}

static uint32_t s_order[2];
static int s_n;

static void record_order(uint32_t line) {
    if (s_n < 2) s_order[s_n++] = line;
}

static void test_priority_order_on_dispatch(void) {
    reset_all();
    intc_enable(0x7U);
    /* Raise UART(0) and DMA(2): DMA must dispatch first (TIMER > DMA > UART). */
    vlab_test_raise_irq(VLAB_IRQ_UART);
    vlab_test_raise_irq(VLAB_IRQ_DMA);
    s_n = 0;
    isr_register(VLAB_IRQ_UART, record_order);
    isr_register(VLAB_IRQ_DMA, record_order);
    assert(isr_dispatch() == 2);
    assert(s_n == 2 && s_order[0] == VLAB_IRQ_DMA && s_order[1] == VLAB_IRQ_UART);
    isr_register(VLAB_IRQ_UART, 0);
    isr_register(VLAB_IRQ_DMA, 0);
    intc_enable(0U);
}

static void test_line_count_configurable(void) {
    reset_all();
    intc_enable(0x7U);
    /* A 2-line platform ignores line 2: no handler runs, and the ACK
     * read still carries its hardware side effect (PENDING->ACTIVE), so
     * the IRQ is acknowledged-but-unhandled and ACTIVE must be cleared
     * explicitly. Lesson: configuring fewer lines than the controller
     * has can lose IRQs; size the configuration to the hardware. */
    isr_configure(2U);
    isr_register(VLAB_IRQ_DMA, record_order);
    s_n = 0;
    vlab_test_raise_irq(VLAB_IRQ_DMA);
    assert(isr_dispatch() == 0);
    assert(s_n == 0);
    assert(hal_read_reg(VLAB_INTC_PENDING) == 0U);
    assert(hal_read_reg(VLAB_INTC_ACTIVE) == (1U << VLAB_IRQ_DMA));
    hal_write_reg(VLAB_INTC_CLEAR, VLAB_IRQ_DMA);
    /* Out-of-range counts keep the previous configuration. */
    isr_configure(0U);
    isr_configure(99U);
    assert(isr_dispatch() == 0);
    /* Back to 3 lines: a freshly raised IRQ dispatches normally. */
    isr_configure(VLAB_IRQ_COUNT);
    isr_register(VLAB_IRQ_DMA, record_order);
    vlab_test_raise_irq(VLAB_IRQ_DMA);
    s_n = 0;
    assert(isr_dispatch() == 1);
    assert(s_n == 1 && s_order[0] == VLAB_IRQ_DMA);
    isr_register(VLAB_IRQ_DMA, 0);
    intc_enable(0U);
}

int main(void) {
    test_dispatch_empty();
    test_completion_path();
    test_error_path_and_recover();
    test_submit_lifecycle_guards();
    test_unregistered_line_still_cleared();
    test_priority_order_on_dispatch();
    test_line_count_configurable();
    printf("test_isr: all cases passed (dispatched=%u)\n",
           (unsigned)isr_dispatched_count());
    return 0;
}
