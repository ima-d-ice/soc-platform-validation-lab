/* HAL host backend: bus-simulation primitives for VLAB_HOST_SIM builds.
 *
 * Register traffic routes to the MMIO shim (drivers/mmio.c), which models
 * reset values, W1C, and START self-clear. Volatile temporaries keep the
 * same read/write discipline as silicon. Critical sections use a nesting
 * counter standing in for the IRQ mask bit.
 */
#include "hal.h"

#include "driver_api.h" /* vlab_mmio_read/write (host bus shim) */

uint32_t hal_read_reg(uint32_t addr) {
    /* Volatile temporary: repeated status polls stay separate loads even
     * though the backing store is host memory. */
    volatile uint32_t v = vlab_mmio_read(addr);
    return v;
}

void hal_write_reg(uint32_t addr, uint32_t val) {
    volatile uint32_t v = val;
    vlab_mmio_write(addr, v);
}

static volatile uint32_t s_irq_masked = 0;

uint32_t hal_irq_disable(void) {
    volatile uint32_t prev = s_irq_masked;
    s_irq_masked = 1U;
    return prev;
}

void hal_irq_restore(uint32_t state) { s_irq_masked = state & 1U; }
