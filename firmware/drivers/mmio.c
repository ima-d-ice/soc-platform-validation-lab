/* Host-native MMIO shim.
 *
 * On silicon these would be volatile pointer dereferences. On the host they
 * are backed by a small static table initialised to reset values from
 * docs/soc-spec.md, so driver logic (bit manipulation, sequencing, error
 * checks) can be compiled and unit-tested with the SAME soc_regs.h header
 * used by the soc_c model. System behaviour (timing, IRQs, DMA
 * movement) is modelled in soc_c/ and validated by soc_c/tests/.
 */
#include <stdint.h>

#include "soc_regs.h"

/* Reset values (must match docs/soc-spec.md + configs/regs.yaml). */
static uint32_t s_uart_ctrl = 0x00000000;static uint32_t s_uart_bauddiv = 0x00000000;
static uint32_t s_uart_txdata = 0x00000000;
static uint32_t s_uart_rxdata = 0x00000000;
/* STATUS is derived: TX_EMPTY=1 when idle. RX_VALID tracked via flag. */
static uint32_t s_uart_rx_valid = 0;

static uint32_t s_timer_ctrl = 0x00000000;
static uint32_t s_timer_load = 0x00000000;
static uint32_t s_timer_value = 0x00000000;
static uint32_t s_timer_irq = 0x00000000;

static uint32_t s_dma_src = 0, s_dma_dst = 0, s_dma_len = 0, s_dma_ctrl = 0;
static uint32_t s_dma_status = 0, s_dma_err = 0;

static uint32_t s_intc_enable = 0, s_intc_pending = 0, s_intc_active = 0;

static uint32_t s_perf_cycles = 0, s_perf_mem = 0, s_perf_dma = 0;
static uint32_t s_perf_irq = 0, s_perf_stalls = 0, s_perf_ctrl = 0;

uint32_t vlab_mmio_read(uint32_t addr) {
    switch (addr) {
        case VLAB_UART_TXDATA:
            return 0; /* WO: reads return 0 on host shim */
        case VLAB_UART_RXDATA:
            return s_uart_rxdata & 0xFFU;
        case VLAB_UART_STATUS:
            return (0x2U /* TX_EMPTY */) | ((s_uart_rx_valid & 1U) << 2);
        case VLAB_UART_CTRL:
            return s_uart_ctrl;
        case VLAB_UART_BAUDDIV:
            return s_uart_bauddiv;
        case VLAB_TIMER_CTRL:
            return s_timer_ctrl;
        case VLAB_TIMER_LOAD:
            return s_timer_load;
        case VLAB_TIMER_VALUE:
            return s_timer_value;
        case VLAB_TIMER_IRQ_STATUS:
            return s_timer_irq;
        case VLAB_DMA_SRC:
            return s_dma_src;
        case VLAB_DMA_DST:
            return s_dma_dst;
        case VLAB_DMA_LEN:
            return s_dma_len;
        case VLAB_DMA_CTRL:
            return s_dma_ctrl;
        case VLAB_DMA_STATUS:
            return s_dma_status;
        case VLAB_DMA_ERR_CODE:
            return s_dma_err;
        case VLAB_INTC_ENABLE:
            return s_intc_enable;
        case VLAB_INTC_PENDING:
            return s_intc_pending;
        case VLAB_INTC_ACK: {
            /* Host INTC emulation: highest pending+enabled line in fixed
             * priority order (TIMER > DMA > UART, mirroring the soc_c
             * model). Read-to-ack: clears PENDING, sets ACTIVE. */
            uint32_t gated = s_intc_pending & s_intc_enable;
            uint32_t line = 0xFFFFFFFFU;
            if (gated & (1U << 1)) line = 1U;
            else if (gated & (1U << 2)) line = 2U;
            else if (gated & (1U << 0)) line = 0U;
            if (line == 0xFFFFFFFFU) return 0xFFFFFFFFU;
            s_intc_pending &= ~(1U << line);
            s_intc_active |= (1U << line);
            return line;
        }
        case VLAB_INTC_ACTIVE:
            return s_intc_active;
        case VLAB_PERF_CYCLES:
            return s_perf_cycles;
        case VLAB_PERF_MEM_ACC:
            return s_perf_mem;
        case VLAB_PERF_DMA_BYTES:
            return s_perf_dma;
        case VLAB_PERF_IRQ_COUNT:
            return s_perf_irq;
        case VLAB_PERF_STALLS:
            return s_perf_stalls;
        case VLAB_PERF_CTRL:
            return s_perf_ctrl;
        default:
            return 0;
    }
}

void vlab_mmio_write(uint32_t addr, uint32_t val) {
    switch (addr) {
        case VLAB_UART_TXDATA:
            s_uart_txdata = val & 0xFFU;
            /* Loopback immediately on host shim. */
            s_uart_rxdata = s_uart_txdata;
            s_uart_rx_valid = 1;
            break;
        case VLAB_UART_CTRL:
            s_uart_ctrl = val;
            break;
        case VLAB_UART_BAUDDIV:
            s_uart_bauddiv = val;
            break;
        case VLAB_TIMER_CTRL:
            s_timer_ctrl = val;
            break;
        case VLAB_TIMER_LOAD:
            s_timer_load = val;
            break;
        case VLAB_TIMER_IRQ_STATUS:
            if (val & 0x1U) s_timer_irq &= ~0x1U;
            break;
        case VLAB_TIMER_IRQ_CLEAR:
            if (val & 0x1U) s_timer_irq &= ~0x1U;
            break;
        case VLAB_DMA_SRC:
            s_dma_src = val;
            break;
        case VLAB_DMA_DST:
            s_dma_dst = val;
            break;
        case VLAB_DMA_LEN:
            s_dma_len = val;
            break;
        case VLAB_DMA_CTRL:
            /* START self-clears; a fresh transfer sets BUSY and clears any
             * sticky DONE/ERROR (mirrors Dma._start). */
            if (val & 0x1U) {
                s_dma_status = 0x1U; /* BUSY */
                s_dma_err = 0;
            }
            s_dma_ctrl = val & ~0x1U;
            break;
        case VLAB_DMA_IRQ_CLEAR:
            /* Shim simplification: clears BUSY too (no engine runs here;
             * real completion/error paths set flags via test hooks). */
            s_dma_status = 0;
            s_dma_err = 0;
            break;
        case VLAB_INTC_ENABLE:
            s_intc_enable = val & 0x7U;
            break;
        case VLAB_INTC_CLEAR:
            s_intc_active &= ~(1U << (val & 0x1FU));
            break;
        case VLAB_PERF_CYCLES:
            s_perf_cycles = val;
            break;
        case VLAB_PERF_MEM_ACC:
            s_perf_mem = val;
            break;
        case VLAB_PERF_DMA_BYTES:
            s_perf_dma = val;
            break;
        case VLAB_PERF_IRQ_COUNT:
            s_perf_irq = val;
            break;
        case VLAB_PERF_STALLS:
            s_perf_stalls = val;
            break;
        case VLAB_PERF_CTRL:
            s_perf_ctrl = val;
            if (val & 0x2U) {
                s_perf_cycles = s_perf_mem = s_perf_dma = 0;
                s_perf_irq = s_perf_stalls = 0;
            }
            break;
        default:
            break;
    }
    /* Host shim: reading RXDATA clears RX_VALID (mirrors soc_c model). */
    (void)0;
}

/* Internal helper used by uart driver shim to consume RX_VALID. */
void vlab_mmio_consume_rx(void) { s_uart_rx_valid = 0; }

/* Test hooks (tests only): drive engine/IRQ events the host has no
 * hardware for, so ISR dispatch paths execute for real. */
void vlab_test_raise_irq(uint32_t line) {
    if (line < 3U) s_intc_pending |= (1U << line);
}

void vlab_test_dma_complete(void) {
    s_dma_status = 0x2U; /* DONE */
    if (s_dma_ctrl & 0x2U) s_intc_pending |= (1U << 2); /* IRQ iff enabled */
}

void vlab_test_dma_error(uint32_t code) {
    s_dma_status = 0x4U; /* ERROR */
    s_dma_err = code;
    if (s_dma_ctrl & 0x2U) s_intc_pending |= (1U << 2); /* IRQ iff enabled */
}
