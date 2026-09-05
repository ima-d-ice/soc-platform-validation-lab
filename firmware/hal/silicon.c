/* HAL silicon backend: real volatile MMIO + PRIMASK critical sections.
 *
 * Linked instead of hal/host.c for non-VLAB_HOST_SIM (freestanding ARM)
 * builds. Not compiled on the host; kept small and reviewable so the
 * host-tested driver logic above it transfers unchanged.
 */
#include "hal.h"

#include "soc_regs.h"

uint32_t hal_read_reg(uint32_t addr) { return *(volatile uint32_t *)addr; }

void hal_write_reg(uint32_t addr, uint32_t val) {
    *(volatile uint32_t *)addr = val;
}

uint32_t hal_irq_disable(void) {
    /* Read + set PRIMASK (or equivalent), return previous state. */
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
