/* HAL implementation. See include/hal.h for the contract. */
#include "hal.h"

#include "soc_regs.h"

#ifdef VLAB_HOST_SIM
#include "driver_api.h" /* vlab_mmio_read/write (host bus shim) */
#endif

uint32_t hal_read_reg(uint32_t addr) {
#ifdef VLAB_HOST_SIM
    /* Volatile temporary: repeated status polls stay separate loads even
     * though the backing store is host memory. */
    volatile uint32_t v = vlab_mmio_read(addr);
    return v;
#else
    return *(volatile uint32_t *)addr;
#endif
}

void hal_write_reg(uint32_t addr, uint32_t val) {
#ifdef VLAB_HOST_SIM
    volatile uint32_t v = val;
    vlab_mmio_write(addr, v);
#else
    *(volatile uint32_t *)addr = val;
#endif
}

void hal_set_bits(uint32_t addr, uint32_t mask) {
    volatile uint32_t cur = hal_read_reg(addr);
    hal_write_reg(addr, cur | mask);
}

void hal_clear_bits(uint32_t addr, uint32_t mask) {
    volatile uint32_t cur = hal_read_reg(addr);
    hal_write_reg(addr, cur & (uint32_t)~mask);
}

void hal_modify_reg(uint32_t addr, uint32_t mask, uint32_t val) {
    volatile uint32_t cur = hal_read_reg(addr);
    hal_write_reg(addr, (cur & (uint32_t)~mask) | (val & mask));
}

#ifdef VLAB_HOST_SIM
/* Host critical-section model: nesting counter standing in for the IRQ
 * mask bit. Drivers use disable/restore pairs so the structure is
 * correct; on silicon the body becomes mask/unmask instructions. */
static volatile uint32_t s_irq_masked = 0;

uint32_t hal_irq_disable(void) {
    volatile uint32_t prev = s_irq_masked;
    s_irq_masked = 1U;
    return prev;
}

void hal_irq_restore(uint32_t state) { s_irq_masked = state & 1U; }
#else
uint32_t hal_irq_disable(void) {
    /* Silicon: read + set PRIMASK (or equivalent), return previous. */
    uint32_t prev;
    __asm__ volatile("mrs %0, primask" : "=r"(prev));
    __asm__ volatile("cpsid i");
    return prev;
}

void hal_irq_restore(uint32_t state) {
    if (!state) {
        __asm__ volatile("cpsie i");
    }
}
#endif
