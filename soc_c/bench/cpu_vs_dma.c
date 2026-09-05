/* CPU vs DMA benchmark in C. Ports benchmarks/cpu_vs_dma.py (core math).
 * Prints CSV: size,burst,words,bursts,dma_ticks,cpu_ticks.
 * CPU copy 3 ticks/word (spec); DMA words*1+(bursts-1).
 */
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

int main(void) {
    static const uint32_t sizes[] = {16, 64, 256, 1024, 4096, 16384};
    static const uint32_t bursts[] = {1, 2, 4, 8, 16};
    size_t si, bi;
    printf("size,burst,words,bursts,dma_ticks,cpu_ticks\n");
    for (si = 0; si < sizeof(sizes) / sizeof(sizes[0]); si++) {
        for (bi = 0; bi < sizeof(bursts) / sizeof(bursts[0]); bi++) {
            soc_t s;
            soc_config_t cfg;
            ctx_t pc;
            uint32_t words, nbursts, cpu_ticks;
            int dma_ticks, i;
            soc_config_default(&cfg);
            cfg.dma_burst = bursts[bi];
            soc_init(&s, &cfg);
            soc_boot(&s, NULL, 0);
            pc.s = &s;
            for (i = 0; i < (int)(sizes[si] / 4); i++)
                soc_sram_write_word(&s, SOC_SRAM_BASE + i * 4,
                                    0xA5000000U | (uint32_t)i);
            soc_write(&s, SRC, SOC_SRAM_BASE);
            soc_write(&s, DST, SOC_SRAM_BASE + 0x8000);
            soc_write(&s, LEN, sizes[si]);
            soc_write(&s, CTRL, 0x1);
            dma_ticks = soc_run_until(&s, pred_done, &pc, 100000);
            words = sizes[si] / 4;
            nbursts = (words + bursts[bi] - 1) / bursts[bi];
            cpu_ticks = words * 3;
            /* Byte-compare destinations. */
            for (i = 0; i < (int)words; i++) {
                uint32_t a = 0, b = 0;
                soc_sram_read_word(&s, SOC_SRAM_BASE + i * 4, &a);
                soc_sram_read_word(&s, SOC_SRAM_BASE + 0x8000 + i * 4, &b);
                if (a != b) {
                    printf("MISMATCH size=%u burst=%u\n", sizes[si],
                           bursts[bi]);
                    return 1;
                }
            }
            printf("%u,%u,%u,%u,%d,%u\n", sizes[si], bursts[bi], words,
                   nbursts, dma_ticks, cpu_ticks);
        }
    }
    return 0;
}
