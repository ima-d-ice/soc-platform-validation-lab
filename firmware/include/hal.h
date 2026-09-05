/* Hardware Abstraction Layer: single door for all register access.
 *
 * On silicon (non-VLAB_HOST_SIM builds) these are volatile pointer
 * dereferences, so the compiler can neither elide repeated reads (status
 * polling) nor reorder accesses across sequence points the way it could
 * with plain memory. On the host (VLAB_HOST_SIM, defined by CMake) they
 * route to the MMIO shim, but still pass through volatile-qualified
 * temporaries so driver code keeps the same read/write discipline and the
 * same compiler barriers as on hardware.
 *
 * hal_irq_disable/hal_irq_restore model critical sections: on silicon
 * these would mask/unmask the interrupt controller (or PRIMASK); on the
 * host they manipulate a nesting counter. They exist so driver code can
 * protect state shared with ISRs with the correct structure.
 */
#ifndef VLAB_HAL_H
#define VLAB_HAL_H

#include <stdint.h>

uint32_t hal_read_reg(uint32_t addr);
void hal_write_reg(uint32_t addr, uint32_t val);
void hal_set_bits(uint32_t addr, uint32_t mask);
void hal_clear_bits(uint32_t addr, uint32_t mask);

/* Read-modify-write: reg = (reg & ~mask) | (val & mask). */
void hal_modify_reg(uint32_t addr, uint32_t mask, uint32_t val);

/* Enter a critical section; returns previous IRQ state for restore. */
uint32_t hal_irq_disable(void);
void hal_irq_restore(uint32_t state);

#endif /* VLAB_HAL_H */
