/* DMA burst timing in C. Ports validation/dma/test_dma_burst.py.
 * ticks = words*latency + (bursts-1), bursts=ceil(words/burst).
 */
#include <assert.h>
#include <stdio.h>

#include "soc.h"

#define SRC (SOC_DMA_BASE + 0x00)
#define DST (SOC_DMA_BASE + 0x04)
#define LEN (SOC_DMA_BASE + 0x08)
#define CTRL (SOC_DMA_BASE + 0x0C)
#define STATUS (SOC_DMA_BASE + 0x10)
#define DONE (1U << 1)
#define ERROR (1U << 2)

typedef struct {
    soc_t *s;
} ctx_t;

static int pred_done(void *c) {
    ctx_t *p = (ctx_t *)c;
    uint32_t st = 0;
    soc_read(p->s, STATUS, &st);
    return (st & (DONE | ERROR)) ? 1 : 0;
}

static int measure_ticks(uint32_t burst, uint32_t nbytes) {
    soc_t s;
    soc_config_t cfg;
    ctx_t pc;
    soc_config_default(&cfg);
    cfg.dma_burst = burst;
    soc_init(&s, &cfg);
    soc_boot(&s, NULL, 0);
    pc.s = &s;
    assert(soc_write(&s, SRC, SOC_SRAM_BASE) == SOC_OK);
    assert(soc_write(&s, DST, SOC_SRAM_BASE + 0x8000) == SOC_OK);
    assert(soc_write(&s, LEN, nbytes) == SOC_OK);
    assert(soc_write(&s, CTRL, 0x1) == SOC_OK);
    return soc_run_until(&s, pred_done, &pc, 100000);
}

int main(void) {
    /* 16 words: burst1 -> 16 + 15 = 31; burst4 -> 16 + 3 = 19. */
    assert(measure_ticks(1, 64) == 31);
    assert(measure_ticks(4, 64) == 19);
    /* 16KB: words=4096, burst16 -> 4096 + 255 = 4351; burst1 -> 4096+4095=8191. */
    assert(measure_ticks(16, 16384) == 4351);
    assert(measure_ticks(1, 16384) == 8191);
    /* Deterministic across reps. */
    assert(measure_ticks(4, 1024) == measure_ticks(4, 1024));
    printf("DMA_BURST OK\n");
    return 0;
}
