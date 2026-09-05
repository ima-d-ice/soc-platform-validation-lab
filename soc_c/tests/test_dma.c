/* DMA validation in C. Ports validation/dma/test_dma.py. */
#include <assert.h>
#include <stdio.h>

#include "soc.h"

#define SRC (SOC_DMA_BASE + 0x00)
#define DST (SOC_DMA_BASE + 0x04)
#define LEN (SOC_DMA_BASE + 0x08)
#define CTRL (SOC_DMA_BASE + 0x0C)
#define STATUS (SOC_DMA_BASE + 0x10)
#define IRQ_CLEAR (SOC_DMA_BASE + 0x14)
#define ERR_CODE (SOC_DMA_BASE + 0x18)

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
    uint32_t mask;
} pred_ctx_t;

static int pred_done_or_error(void *ctx) {
    pred_ctx_t *p = (pred_ctx_t *)ctx;
    uint32_t st = 0;
    soc_read(p->s, STATUS, &st);
    return (st & (DONE | ERROR)) ? 1 : 0;
}

int main(void) {
    soc_t s;
    soc_config_t cfg;
    uint32_t v = 0;
    int i;

    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    soc_boot(&s, NULL, 0);

    /* Completes: 16 words SRAM->SRAM with IRQ. */
    {
        uint32_t src = SOC_SRAM_BASE, dst = SOC_SRAM_BASE + 0x1000;
        pred_ctx_t pc = {&s, DONE | ERROR};
        for (i = 0; i < 16; i++)
            assert(soc_sram_write_word(&s, src + i * 4, 0xA5000000U | (uint32_t)i) == SOC_OK);
        assert(soc_write(&s, INTC_ENABLE, 1U << IRQ_DMA) == SOC_OK);
        assert(soc_write(&s, SRC, src) == SOC_OK);
        assert(soc_write(&s, DST, dst) == SOC_OK);
        assert(soc_write(&s, LEN, 16 * 4) == SOC_OK);
        assert(soc_write(&s, CTRL, 0x3) == SOC_OK);
        assert(soc_run_until(&s, pred_done_or_error, &pc, 1000) >= 0);
        assert(soc_read(&s, STATUS, &v) == SOC_OK && (v & DONE));
        assert(!(v & ERROR));
        for (i = 0; i < 16; i++) {
            assert(soc_sram_read_word(&s, dst + i * 4, &v) == SOC_OK &&
                   v == (0xA5000000U | (uint32_t)i));
        }
        assert(soc_read(&s, ERR_CODE, &v) == SOC_OK && v == 0);
        assert(soc_read(&s, INTC_PENDING, &v) == SOC_OK && (v & (1U << IRQ_DMA)));
        assert(soc_read(&s, INTC_ACK, &v) == SOC_OK && v == IRQ_DMA);
        assert(soc_write(&s, INTC_CLEAR, IRQ_DMA) == SOC_OK);
        assert(soc_write(&s, IRQ_CLEAR, 1) == SOC_OK);
        assert(soc_read(&s, SOC_PERF_BASE + 0x08, &v) == SOC_OK && v == 16 * 4);
    }

    /* Invalid address -> ERR_ADDR=1. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SRC, 0x30000000U) == SOC_OK);
    assert(soc_write(&s, DST, SOC_SRAM_BASE) == SOC_OK);
    assert(soc_write(&s, LEN, 16) == SOC_OK);
    assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
    soc_step(&s, 2);
    assert(soc_read(&s, STATUS, &v) == SOC_OK && (v & ERROR));
    assert(soc_read(&s, ERR_CODE, &v) == SOC_OK && v == 1);

    /* Misaligned -> ERR_ALIGN=2. */
    soc_boot(&s, NULL, 0);
    assert(soc_write(&s, SRC, SOC_SRAM_BASE + 1) == SOC_OK);
    assert(soc_write(&s, DST, SOC_SRAM_BASE + 0x1000) == SOC_OK);
    assert(soc_write(&s, LEN, 16) == SOC_OK);
    assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
    soc_step(&s, 2);
    assert(soc_read(&s, STATUS, &v) == SOC_OK && (v & ERROR));
    assert(soc_read(&s, ERR_CODE, &v) == SOC_OK && v == 2);

    /* Bad lengths -> ERR_LEN=3. */
    {
        uint32_t bads[3] = {0, 3, 6};
        for (i = 0; i < 3; i++) {
            soc_boot(&s, NULL, 0);
            assert(soc_write(&s, SRC, SOC_SRAM_BASE) == SOC_OK);
            assert(soc_write(&s, DST, SOC_SRAM_BASE + 0x1000) == SOC_OK);
            assert(soc_write(&s, LEN, bads[i]) == SOC_OK);
            assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
            soc_step(&s, 2);
            assert(soc_read(&s, STATUS, &v) == SOC_OK && (v & ERROR));
            assert(soc_read(&s, ERR_CODE, &v) == SOC_OK && v == 3);
            assert(soc_write(&s, IRQ_CLEAR, 1) == SOC_OK);
        }
    }

    /* START while busy ignored + stall counted. */
    {
        uint32_t stalls_before = 0, stalls_after = 0;
        soc_boot(&s, NULL, 0);
        assert(soc_write(&s, SRC, SOC_SRAM_BASE) == SOC_OK);
        assert(soc_write(&s, DST, SOC_SRAM_BASE + 0x2000) == SOC_OK);
        assert(soc_write(&s, LEN, 64) == SOC_OK);
        assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
        assert(soc_read(&s, STATUS, &v) == SOC_OK && (v & BUSY));
        assert(soc_read(&s, SOC_PERF_BASE + 0x10, &stalls_before) == SOC_OK);
        assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
        assert(soc_read(&s, STATUS, &v) == SOC_OK && (v & BUSY));
        assert(soc_read(&s, SOC_PERF_BASE + 0x10, &stalls_after) == SOC_OK &&
               stalls_after >= stalls_before + 1);
    }

    printf("DMA OK\n");
    return 0;
}
