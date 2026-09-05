/* Unit tests for DMA capabilities (GENERAL CONCEPT + VLAB PLATFORM).
 *
 * A synthetic DRAM/peripheral map proves validation follows caps + regions
 * rather than VLAB's SRAM-only assumptions. Each case states whether the
 * failure is invalid driver-API use (LEN/ALIGN/ADDR) or unsupported by the
 * configured platform (UNSUPPORTED).
 */
#include <assert.h>
#include <stdio.h>

#include "dma_caps.h"
#include "driver_api.h"
#include "hal.h"
#include "mem_regions.h"
#include "soc_regs.h"

#define SRAM_BASE 0x10000000U
#define DRAM_BASE 0x40000000U
#define PERIPH_BASE 0x20002000U

static const struct memory_region s_map[] = {
    {"sram", SRAM_BASE, 0x10000U, MEM_TYPE_SRAM, MEM_PERM_R | MEM_PERM_W},
    {"dram", DRAM_BASE, 0x100000U, MEM_TYPE_DRAM, MEM_PERM_R | MEM_PERM_W},
    {"periph", PERIPH_BASE, 0x1000U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
};
#define MAP_N ((uint32_t)(sizeof(s_map) / sizeof(s_map[0])))

static const struct dma_caps s_open_caps = {
    4U, 0U, true, true, true, true, false /* align, max(0=unlimited),
                                              ram2ram, m2p, p2m, irq, cancel */
};

static void use_open(void) { dma_configure(s_map, MAP_N, &s_open_caps); }

static void test_dram_mem_to_mem(void) {
    use_open();
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    /* DRAM behaves like SRAM when caps allow it (not a VLAB transfer). */
    assert(dma_start(DRAM_BASE, DRAM_BASE + 0x1000U, 64, 0) == VLAB_DMA_OK);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
}

static void test_periph_directions_follow_caps(void) {
    static const struct dma_caps no_periph = {4U, 0U, true, false, false,
                                              true, false};
    use_open();
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(PERIPH_BASE, SRAM_BASE, 16, 0) == VLAB_DMA_OK);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(SRAM_BASE, PERIPH_BASE, 16, 0) == VLAB_DMA_OK);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    /* Same mapped endpoints, restricted caps: platform, not API, refuses. */
    dma_configure(s_map, MAP_N, &no_periph);
    assert(dma_start(PERIPH_BASE, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(SRAM_BASE, PERIPH_BASE, 16, 0) == VLAB_DMA_ERR_UNSUPPORTED);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 16, 0) == VLAB_DMA_OK);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
}

static void test_max_transfer_is_platform_limit(void) {
    static const struct dma_caps small_max = {4U, 64U, true, false, false,
                                              true, false};
    dma_configure(s_map, MAP_N, &small_max);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 128, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED); /* valid use, over platform max */
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 64, 0) == VLAB_DMA_OK);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
}

static void test_invalid_use_codes_unchanged(void) {
    use_open();
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 0, 0) == VLAB_DMA_ERR_LEN);
    assert(dma_start(SRAM_BASE + 1U, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ALIGN);
    assert(dma_start(0x30000000U, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ADDR);
    /* Wrapping range is unmapped, not merely unsupported. */
    assert(dma_start(0xFFFFFFFCU, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ADDR);
}

static void test_helpers_directly(void) {
    assert(dma_endpoint_type(s_map, MAP_N, SRAM_BASE, 16) == (int)DMA_ADDR_MEM);
    assert(dma_endpoint_type(s_map, MAP_N, DRAM_BASE, 16) == (int)DMA_ADDR_MEM);
    assert(dma_endpoint_type(s_map, MAP_N, PERIPH_BASE, 16) ==
           (int)DMA_ADDR_PERIPHERAL);
    assert(dma_endpoint_type(s_map, MAP_N, 0x30000000U, 16) < 0);
    assert(dma_address_valid(s_map, MAP_N, &s_open_caps, SRAM_BASE, 16,
                             (int)DMA_ADDR_MEM));
    assert(!dma_address_valid(s_map, MAP_N, &s_open_caps, SRAM_BASE + 1U, 16,
                              (int)DMA_ADDR_MEM));
    assert(dma_direction_supported(&s_open_caps, (int)DMA_ADDR_MEM,
                                   (int)DMA_ADDR_PERIPHERAL));
    assert(!dma_direction_supported(&s_open_caps, (int)DMA_ADDR_PERIPHERAL,
                                    (int)DMA_ADDR_PERIPHERAL));
}

static void test_vlab_defaults(void) {
    dma_init(); /* VLAB platform: SRAM-only, align 4, max 16KB */
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 16384, 0) == VLAB_DMA_OK);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 16385U & ~3U, 0) ==
           VLAB_DMA_OK); /* 16384 aligned down: still at max */
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
    assert(dma_start(SRAM_BASE, SRAM_BASE + 0x1000U, 16388, 0) ==
           VLAB_DMA_ERR_UNSUPPORTED); /* over VLAB max */
    /* 0x40000000 is unmapped on VLAB even though the helper map has DRAM. */
    assert(dma_start(0x40000000U, SRAM_BASE, 16, 0) == VLAB_DMA_ERR_ADDR);
    hal_write_reg(VLAB_DMA_IRQ_CLEAR, 1U);
}

int main(void) {
    test_dram_mem_to_mem();
    test_periph_directions_follow_caps();
    test_max_transfer_is_platform_limit();
    test_invalid_use_codes_unchanged();
    test_helpers_directly();
    test_vlab_defaults();
    dma_init(); /* leave VLAB defaults installed for later suites */
    printf("test_dma_caps: all cases passed\n");
    return 0;
}
