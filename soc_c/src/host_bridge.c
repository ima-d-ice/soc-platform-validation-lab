#include "host_bridge.h"

static soc_t g_soc;
static int g_inited = 0;

soc_t *soc_host_soc(void) {
    if (!g_inited) soc_host_init(NULL);
    return &g_soc;
}

void soc_host_init(const soc_config_t *cfg) {
    soc_config_t dflt;
    if (!cfg) {
        soc_config_default(&dflt);
        cfg = &dflt;
    }
    soc_init(&g_soc, cfg);
    g_inited = 1;
}

void soc_host_boot(void) {
    if (!g_inited) soc_host_init(NULL);
    soc_boot(&g_soc, NULL, 0);
}

void soc_host_step(uint32_t n) {
    if (!g_inited) soc_host_init(NULL);
    soc_step(&g_soc, n);
}

uint32_t vlab_mmio_read(uint32_t addr) {
    uint32_t v = 0;
    if (!g_inited) soc_host_init(NULL);
    if (soc_read(&g_soc, addr, &v) != SOC_OK) return 0;
    return v;
}

void vlab_mmio_write(uint32_t addr, uint32_t val) {
    if (!g_inited) soc_host_init(NULL);
    (void)soc_write(&g_soc, addr, val);
}

void vlab_test_raise_irq(uint32_t line) {
    if (!g_inited) soc_host_init(NULL);
    soc_intc_raise(&g_soc.intc, (int)line);
}

void vlab_test_dma_complete(void) {
    /* Drive a BUSY engine to its terminal flag via stepping (no shortcut
     * writes). Idle engine: nothing to drive, return immediately. */
    uint32_t st = 0;
    int i;
    if (!g_inited) return;
    for (i = 0; i < 100000; i++) {
        soc_read(&g_soc, SOC_DMA_BASE + 0x10, &st);
        if (st & (SOC_DMA_STATUS_DONE | SOC_DMA_STATUS_ERROR)) break;
        if (!(st & SOC_DMA_STATUS_BUSY)) break;
        soc_step(&g_soc, 1);
    }
}

void vlab_test_dma_error(uint32_t code) {
    if (!g_inited) return;
    g_soc.dma.busy = 0;
    g_soc.dma.done = 0;
    g_soc.dma.error = 1;
    g_soc.dma.err_code = code;
    /* Real engines raise on ERROR iff IRQ was enabled at START. */
    if (g_soc.dma.ctrl & SOC_DMA_CTRL_IRQ_ENABLE)
        soc_intc_raise(&g_soc.intc, SOC_DMA_IRQ_LINE);
}
