#include "driver_api.h"
#include "soc_regs.h"

/* Burst size is platform-config only (configs dir, dma_burst key); no BURST
 * register. Completion and error both raise the DMA INTC line when
 * irq_enable is set. Clearing is two-step: dma_clear() clears DMA flags,
 * then intc_clear(2) clears the pending bit. */

#define SRAM_BASE 0x10000000U
#define SRAM_SIZE 0x00010000U

static int in_sram(uint32_t addr, uint32_t len) {
    if (len == 0) return 0;
    if (addr < SRAM_BASE) return 0;
    if (addr + len < addr) return 0; /* wrap */
    return (addr + len) <= (SRAM_BASE + SRAM_SIZE);
}

int dma_start(uint32_t src, uint32_t dst, uint32_t len, int irq_enable) {
    uint32_t st = vlab_mmio_read(VLAB_DMA_STATUS);
    if (st & VLAB_DMA_STATUS_BUSY) return VLAB_DMA_ERR_BUSY;
    if (len == 0 || (len % 4U) != 0) return VLAB_DMA_ERR_LEN;
    if ((src % 4U) != 0 || (dst % 4U) != 0) return VLAB_DMA_ERR_ALIGN;
    if (!in_sram(src, len) || !in_sram(dst, len)) return VLAB_DMA_ERR_ADDR;
    vlab_mmio_write(VLAB_DMA_SRC, src);
    vlab_mmio_write(VLAB_DMA_DST, dst);
    vlab_mmio_write(VLAB_DMA_LEN, len);
    vlab_mmio_write(VLAB_DMA_CTRL, VLAB_DMA_CTRL_START |
                                       (irq_enable ? VLAB_DMA_CTRL_IRQ_ENABLE : 0U));
    return VLAB_DMA_OK;
}

uint32_t dma_status(void) { return vlab_mmio_read(VLAB_DMA_STATUS); }

void dma_clear(void) { vlab_mmio_write(VLAB_DMA_IRQ_CLEAR, 1U); }

uint32_t dma_err_code(void) { return vlab_mmio_read(VLAB_DMA_ERR_CODE); }
