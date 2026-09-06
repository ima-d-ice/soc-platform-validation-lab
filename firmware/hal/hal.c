/* HAL core: device-free read-modify-write helpers over read/write.
 *
 * This file knows nothing about UART/TIMER/DMA/INTC semantics; it only
 * combines the backend primitives below. Backend: hal/host.c routes into
 * the live SoC model (see docs/firmware-c.md for the intended silicon
 * mapping: volatile pointers + PRIMASK).
 */
#include "hal.h"

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
