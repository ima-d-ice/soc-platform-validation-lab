/* HAL unit tests: bit helpers + critical-section structure.
 *
 * Runs against the host MMIO shim; asserts real bit-manipulation behavior
 * through hal_read_reg/hal_write_reg. Each case resets the scratch
 * register (UART_BAUDDIV) it uses.
 */
#include <assert.h>
#include <stdio.h>

#include "hal.h"
#include "soc_regs.h"

static void test_read_write_roundtrip(void) {
    hal_write_reg(VLAB_UART_BAUDDIV, 0x12345678U);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0x12345678U);
    hal_write_reg(VLAB_UART_BAUDDIV, 0U);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0U);
}

static void test_set_bits(void) {
    hal_write_reg(VLAB_UART_BAUDDIV, 0x0FU);
    hal_set_bits(VLAB_UART_BAUDDIV, 0xF0U);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0xFFU);
    /* Setting already-set bits is idempotent. */
    hal_set_bits(VLAB_UART_BAUDDIV, 0xFFU);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0xFFU);
    hal_write_reg(VLAB_UART_BAUDDIV, 0U);
}

static void test_clear_bits(void) {
    hal_write_reg(VLAB_UART_BAUDDIV, 0xFFU);
    hal_clear_bits(VLAB_UART_BAUDDIV, 0x0FU);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0xF0U);
    /* Clearing clear bits is a no-op. */
    hal_clear_bits(VLAB_UART_BAUDDIV, 0x0FU);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0xF0U);
    hal_write_reg(VLAB_UART_BAUDDIV, 0U);
}

static void test_modify_reg(void) {
    hal_write_reg(VLAB_UART_BAUDDIV, 0xAAAAAAAAU);
    /* Replace low nibble only: (reg & ~mask) | (val & mask). */
    hal_modify_reg(VLAB_UART_BAUDDIV, 0xFU, 0x5U);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0xAAAAAAA5U);
    /* Val bits outside the mask must not leak through. */
    hal_modify_reg(VLAB_UART_BAUDDIV, 0xFU, 0xFFFFFFFFU);
    assert(hal_read_reg(VLAB_UART_BAUDDIV) == 0xAAAAAAAFU);
    hal_write_reg(VLAB_UART_BAUDDIV, 0U);
}

static void test_irq_disable_restore(void) {
    uint32_t s0 = hal_irq_disable();
    assert(s0 == 0U); /* IRQs start enabled on a fresh shim. */
    /* Nested disable keeps the masked state; restore is ordered. */
    uint32_t s1 = hal_irq_disable();
    assert(s1 == 1U);
    hal_irq_restore(s1);
    hal_irq_restore(s0);
    assert(hal_irq_disable() == 0U);
    hal_irq_restore(0U);
}

int main(void) {
    test_read_write_roundtrip();
    test_set_bits();
    test_clear_bits();
    test_modify_reg();
    test_irq_disable_restore();
    printf("test_hal: all cases passed\n");
    return 0;
}
