/* DMA endpoint matrix at engine level: all three directions move bytes.
 * Ports the validation matrix to soc_c and proves data movement through
 * the UART stream FIFOs (RAM->uart-tx->uart-rx->RAM round-trips
 * byte-identical), plus the ADDR-vs-UNSUPPORTED split, roles, busy, IRQ
 * completion, error completion and recovery.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "soc.h"

#define SRC (SOC_DMA_BASE + 0x00)
#define DST (SOC_DMA_BASE + 0x04)
#define LEN (SOC_DMA_BASE + 0x08)
#define CTRL (SOC_DMA_BASE + 0x0C)
#define STATUS (SOC_DMA_BASE + 0x10)
#define IRQ_CLEAR (SOC_DMA_BASE + 0x14)
#define ERR_CODE (SOC_DMA_BASE + 0x18)

#define UART_TX (SOC_UART_BASE + 0x00)
#define UART_RX (SOC_UART_BASE + 0x04)

#define INTC_ENABLE (SOC_INTC_BASE + 0x00)
#define INTC_PENDING (SOC_INTC_BASE + 0x04)
#define INTC_ACK (SOC_INTC_BASE + 0x08)
#define INTC_CLEAR (SOC_INTC_BASE + 0x0C)

#define IRQ_DMA 2
#define BUSY (1U << 0)
#define DONE (1U << 1)
#define ERROR (1U << 2)

typedef struct {
    soc_t *s;
} ctx_t;

static int pred_term(void *c) {
    ctx_t *p = (ctx_t *)c;
    uint32_t st = 0;
    soc_read(p->s, STATUS, &st);
    return (st & (DONE | ERROR)) ? 1 : 0;
}

static void boot(soc_t *s) {
    soc_config_t cfg;
    soc_config_default(&cfg);
    soc_init(s, &cfg);
    soc_boot(s, NULL, 0);
}

static void start(soc_t *s, uint32_t src, uint32_t dst, uint32_t len,
                  uint32_t ctrl) {
    assert(soc_write(s, SRC, src) == SOC_OK);
    assert(soc_write(s, DST, dst) == SOC_OK);
    assert(soc_write(s, LEN, len) == SOC_OK);
    assert(soc_write(s, CTRL, ctrl) == SOC_OK);
}

static uint32_t status(soc_t *s) {
    uint32_t v = 0;
    assert(soc_read(s, STATUS, &v) == SOC_OK);
    return v;
}

static uint32_t errcode(soc_t *s) {
    uint32_t v = 0;
    assert(soc_read(s, ERR_CODE, &v) == SOC_OK);
    return v;
}

/* Fresh SoC per burst cell; returns transfer ticks to DONE/ERROR. */
static int measure_ticks(uint32_t burst, uint32_t nbytes) {
    soc_t m;
    soc_config_t cfg;
    ctx_t q;
    soc_config_default(&cfg);
    cfg.dma_burst = burst;
    soc_init(&m, &cfg);
    soc_boot(&m, NULL, 0);
    q.s = &m;
    start(&m, SOC_SRAM_BASE, SOC_SRAM_BASE + 0x8000, nbytes, 0x1);
    return soc_run_until(&m, pred_term, &q, 100000);
}

int main(void) {
    soc_t s;
    ctx_t pc;
    uint32_t v = 0;
    int i;

    /* Valid RAM -> Peripheral: bytes land in the TX stream. */
    boot(&s);
    pc.s = &s;
    for (i = 0; i < 16; i++)
        assert(soc_sram_write_word(&s, SOC_SRAM_BASE + i * 4,
                                   0xA5000000U | (uint32_t)i) == SOC_OK);
    assert(soc_write(&s, INTC_ENABLE, 1U << IRQ_DMA) == SOC_OK);
    start(&s, SOC_SRAM_BASE, UART_TX, 64, 0x3);
    assert(soc_run_until(&s, pred_term, &pc, 100000) >= 0);
    assert(status(&s) & DONE);
    assert(s.uart.dma_tx_len == 64);
    for (i = 0; i < 16; i++) {
        uint32_t w = ((uint32_t)s.uart.dma_tx_fifo[i * 4]) |
                     ((uint32_t)s.uart.dma_tx_fifo[i * 4 + 1] << 8) |
                     ((uint32_t)s.uart.dma_tx_fifo[i * 4 + 2] << 16) |
                     ((uint32_t)s.uart.dma_tx_fifo[i * 4 + 3] << 24);
        assert(w == (0xA5000000U | (uint32_t)i));
    }
    /* Completion IRQ arrived on line 2; two-step clear. */
    assert(soc_read(&s, INTC_PENDING, &v) == SOC_OK && (v & (1U << IRQ_DMA)));
    assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == IRQ_DMA);
    assert(soc_write(&s, INTC_CLEAR, IRQ_DMA) == SOC_OK);
    assert(soc_write(&s, IRQ_CLEAR, 1) == SOC_OK);
    assert(soc_read(&s, SOC_PERF_BASE + 0x08, &v) == SOC_OK && v == 64);

    /* Valid Peripheral -> RAM: looped-back bytes drain out identical. */
    start(&s, UART_RX, SOC_SRAM_BASE + 0x2000, 64, 0x1);
    assert(soc_run_until(&s, pred_term, &pc, 100000) >= 0);
    assert(status(&s) & DONE);
    for (i = 0; i < 16; i++) {
        assert(soc_sram_read_word(&s, SOC_SRAM_BASE + 0x2000 + i * 4, &v) ==
                   SOC_OK &&
               v == (0xA5000000U | (uint32_t)i));
    }
    assert(s.uart.dma_rx_len == 0); /* drained */

    /* Valid RAM -> RAM still works (existing behavior preserved). */
    boot(&s);
    start(&s, SOC_SRAM_BASE, SOC_SRAM_BASE + 0x1000, 64, 0x1);
    assert(soc_run_until(&s, pred_term, &pc, 100000) >= 0);
    assert(status(&s) & DONE);

    /* ADDR vs UNSUPPORTED split. */
    boot(&s);
    start(&s, 0x30000000U, SOC_SRAM_BASE, 16, 0x1); /* unmapped src */
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 1);
    start(&s, SOC_SRAM_BASE, 0x30000000U, 16, 0x1); /* unmapped dst */
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 1);
    start(&s, 0xFFFFFFFCU, SOC_SRAM_BASE, 16, 0x1); /* overflow */
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 1);
    /* Mapped but incapable: TIMER/DMA/INTC/PERF regs. */
    start(&s, SOC_SRAM_BASE, SOC_TIMER_BASE, 16, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4);
    start(&s, SOC_TIMER_BASE + 0x04, SOC_SRAM_BASE, 16, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4);
    start(&s, SOC_SRAM_BASE, SOC_DMA_BASE, 16, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4);
    /* Wrong FIFO roles. */
    start(&s, SOC_SRAM_BASE, UART_RX, 16, 0x1); /* rx is source-only */
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4);
    start(&s, UART_TX, SOC_SRAM_BASE, 16, 0x1); /* tx is sink-only */
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4);
    /* Disallowed direction: PERIPH -> PERIPH. */
    start(&s, UART_RX, UART_TX, 16, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4);
    /* Classic invalid uses keep classic codes. */
    start(&s, SOC_SRAM_BASE, SOC_SRAM_BASE + 0x1000, 0, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 3);
    start(&s, SOC_SRAM_BASE + 1, SOC_SRAM_BASE + 0x1000, 16, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 2);
    start(&s, SOC_SRAM_BASE, SOC_SRAM_BASE + 0x1000, 32768, 0x1);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 4); /* over 16KB max */

    /* Busy engine: second START ignored + stall counted. */
    boot(&s);
    start(&s, SOC_SRAM_BASE, SOC_SRAM_BASE + 0x1000, 1024, 0x1);
    assert(status(&s) & BUSY);
    assert(soc_read(&s, SOC_PERF_BASE + 0x10, &v) == SOC_OK);
    {
        uint32_t stalls_before = v;
        assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
        assert(status(&s) & BUSY);
        assert(soc_read(&s, SOC_PERF_BASE + 0x10, &v) == SOC_OK &&
               v >= stalls_before + 1);
    }

    /* Error completion raises IRQ iff enabled; recovery clears all. */
    boot(&s);
    assert(soc_write(&s, INTC_ENABLE, 1U << IRQ_DMA) == SOC_OK);
    start(&s, 0x30000000U, SOC_SRAM_BASE, 16, 0x3);
    soc_step(&s, 2);
    assert(status(&s) & ERROR && errcode(&s) == 1);
    assert(soc_read(&s, INTC_PENDING, &v) == SOC_OK && (v & (1U << IRQ_DMA)));
    assert(soc_write(&s, IRQ_CLEAR, 1) == SOC_OK);
    assert(soc_write(&s, INTC_CLEAR, IRQ_DMA) == SOC_OK);
    assert(status(&s) == 0 && errcode(&s) == 0);

    /* Burst timing: ticks = words*1 + (bursts-1), bursts=ceil(words/burst).
     * Same formula the cpu_vs_dma bench sweeps; pinned here as golden
     * values (16KB: 8191 at burst 1 down to 4351 at burst 16). */
    assert(measure_ticks(1, 64) == 31);
    assert(measure_ticks(4, 64) == 19);
    assert(measure_ticks(16, 16384) == 4351);
    assert(measure_ticks(1, 16384) == 8191);
    assert(measure_ticks(4, 1024) == measure_ticks(4, 1024)); /* deterministic */

    printf("ENDPOINTS OK\n");
    return 0;
}
