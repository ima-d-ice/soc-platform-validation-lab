#include "driver_api.h"
#include "hal.h"
#include "isr.h"
#include "platforms/vlab/platform_vlab.h"
#include "soc_regs.h"

/* DMA consumes platform configuration (memory map + capabilities); it
 * never hard-codes SRAM, alignment, or transfer limits. Default
 * configuration is the VLAB platform (dma_init); dma_configure overrides
 * it. Validation order BUSY/LEN/ALIGN/MAX/ADDR/DIRECTION matches the
 * soc_c model. Completion and error both raise the DMA INTC line when
 * irq_enable is set. Clearing is two-step: dma_clear() clears DMA flags,
 * then intc_clear() clears the pending bit. */

/* Platform configuration (not owned here; init/configure install it). */
static const struct memory_region *s_map = NULL;
static uint32_t s_map_n = 0;
static const struct dma_caps *s_caps = NULL;

/* Interrupt-driven lifecycle state. Volatile: written by dma_isr (ISR
 * context on silicon), read by main-line code. Every cross-context access
 * below goes through these volatiles or a hal critical section. */
static volatile dma_state_t s_state = DMA_S_IDLE;
static volatile uint32_t s_done_flag = 0;
static volatile uint32_t s_err_latch = 0;
static volatile uint32_t s_irq_count = 0;

/* Shared validation, same order as the soc_c model
 * (BUSY/LEN/ALIGN/MAX/ADDR/DIRECTION) so host tests and golden-model
 * tests assert identical behavior. LEN/ALIGN/ADDR mean invalid
 * driver-API use; over-max and disallowed directions mean unsupported by
 * the configured platform. */
static int validate(uint32_t src, uint32_t dst, uint32_t len) {
    uint32_t align;
    int src_type, dst_type;
    if (hal_read_reg(VLAB_DMA_STATUS) & VLAB_DMA_STATUS_BUSY)
        return VLAB_DMA_ERR_BUSY;
    align = (s_caps && s_caps->alignment > 1) ? s_caps->alignment : 1U;
    if (len == 0 || (align > 1 && len % align != 0)) return VLAB_DMA_ERR_LEN;
    if (align > 1 && (src % align != 0 || dst % align != 0))
        return VLAB_DMA_ERR_ALIGN;
    if (s_caps && s_caps->max_transfer && len > s_caps->max_transfer)
        return VLAB_DMA_ERR_UNSUPPORTED;
    src_type = dma_endpoint_type(s_map, s_map_n, src, len);
    dst_type = dma_endpoint_type(s_map, s_map_n, dst, len);
    if (src_type < 0 || dst_type < 0) return VLAB_DMA_ERR_ADDR;
    if (s_caps && !dma_direction_supported(s_caps, src_type, dst_type))
        return VLAB_DMA_ERR_UNSUPPORTED;
    return VLAB_DMA_OK;
}

void dma_init(void) {
    s_map = vlab_memory_map(&s_map_n);
    s_caps = vlab_dma_caps();
}

void dma_configure(const struct memory_region *map, uint32_t n,
                   const struct dma_caps *caps) {
    if (map != NULL && n > 0) {
        s_map = map;
        s_map_n = n;
    }
    if (caps != NULL) {
        s_caps = caps;
    }
}

int dma_start(uint32_t src, uint32_t dst, uint32_t len, int irq_enable) {
    int rc = validate(src, dst, len);
    if (rc != VLAB_DMA_OK) return rc;
    hal_write_reg(VLAB_DMA_SRC, src);
    hal_write_reg(VLAB_DMA_DST, dst);
    hal_write_reg(VLAB_DMA_LEN, len);
    hal_write_reg(VLAB_DMA_CTRL, VLAB_DMA_CTRL_START |
                                     (irq_enable ? VLAB_DMA_CTRL_IRQ_ENABLE : 0U));
    return VLAB_DMA_OK;
}

uint32_t dma_status(void) { return hal_read_reg(VLAB_DMA_STATUS); }

void dma_clear(void) { hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U); }

uint32_t dma_err_code(void) { return hal_read_reg(VLAB_DMA_ERR_CODE); }

int dma_submit(uint32_t src, uint32_t dst, uint32_t len, int irq_enable) {
    /* Critical section: the state check + program + START sequence must be
     * atomic against dma_isr, otherwise an IRQ between validation and START
     * could leave the lifecycle inconsistent. */
    uint32_t key = hal_irq_disable();
    if (s_state != DMA_S_IDLE) {
        hal_irq_restore(key);
        return VLAB_DMA_ERR_BUSY;
    }
    s_state = DMA_S_STARTING;
    int rc = validate(src, dst, len);
    if (rc != VLAB_DMA_OK) {
        s_state = DMA_S_IDLE;
        hal_irq_restore(key);
        return rc;
    }
    s_done_flag = 0;
    s_err_latch = 0;
    hal_write_reg(VLAB_DMA_SRC, src);
    hal_write_reg(VLAB_DMA_DST, dst);
    hal_write_reg(VLAB_DMA_LEN, len);
    hal_write_reg(VLAB_DMA_CTRL, VLAB_DMA_CTRL_START |
                                     (irq_enable ? VLAB_DMA_CTRL_IRQ_ENABLE : 0U));
    s_state = DMA_S_ACTIVE;
    hal_irq_restore(key);
    return VLAB_DMA_OK;
}

dma_state_t dma_state(void) { return s_state; }

int dma_is_complete(void) { return s_done_flag != 0U; }

uint32_t dma_latched_error(void) { return s_err_latch; }

uint32_t dma_irq_count(void) { return s_irq_count; }

void dma_isr(uint32_t line) {
    (void)line;
    uint32_t st = hal_read_reg(VLAB_DMA_STATUS);
    if (st & VLAB_DMA_STATUS_DONE) {
        s_done_flag = 1U;
        s_state = DMA_S_COMPLETE;
    } else if (st & VLAB_DMA_STATUS_ERROR) {
        s_err_latch = hal_read_reg(VLAB_DMA_ERR_CODE);
        s_state = DMA_S_ERROR;
    }
    /* Else: spurious IRQ with no terminal flag; leave state, still clear. */
    dma_clear();
    intc_clear(VLAB_IRQ_DMA);
    s_irq_count++;
}

void dma_recover(void) {
    uint32_t key = hal_irq_disable();
    if (s_state == DMA_S_ERROR || s_state == DMA_S_COMPLETE) {
        s_state = DMA_S_RECOVERY;
        dma_clear();
        intc_clear(VLAB_IRQ_DMA);
        s_done_flag = 0;
        s_err_latch = 0;
        s_state = DMA_S_IDLE;
    }
    hal_irq_restore(key);
}
