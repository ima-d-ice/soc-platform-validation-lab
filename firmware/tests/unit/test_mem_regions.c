/* Unit tests for the generic memory-region helpers (GENERAL CONCEPT).
 *
 * Uses synthetic maps (including DRAM, which VLAB does not have) to prove
 * the helpers are independent of any platform's assumptions.
 */
#include <assert.h>
#include <stdio.h>

#include "mem_regions.h"

#define SRAM_BASE 0x10000000U
#define DRAM_BASE 0x40000000U

static const struct memory_region s_test_map[] = {
    {"sram", SRAM_BASE, 0x10000U, MEM_TYPE_SRAM, MEM_PERM_R | MEM_PERM_W},
    {"dram", DRAM_BASE, 0x100000U, MEM_TYPE_DRAM,
     MEM_PERM_R | MEM_PERM_W | MEM_PERM_X},
    {"uart", 0x20000000U, 0x1000U, MEM_TYPE_MMIO, MEM_PERM_R | MEM_PERM_W},
};
#define TEST_MAP_N ((uint32_t)(sizeof(s_test_map) / sizeof(s_test_map[0])))

static void test_contains_edges(void) {
    const struct memory_region *sram = &s_test_map[0];
    assert(memory_region_contains(sram, SRAM_BASE, 4));
    assert(memory_region_contains(sram, SRAM_BASE + 0x10000U - 4U, 4));
    assert(!memory_region_contains(sram, SRAM_BASE + 0x10000U - 3U, 4));
    assert(!memory_region_contains(sram, SRAM_BASE, 0));
    assert(!memory_region_contains(sram, 0x20000000U, 4));
    assert(!memory_region_contains(NULL, SRAM_BASE, 4));
}

static void test_overflow(void) {
    assert(memory_range_overflows(0xFFFFFFFFU, 4));
    assert(memory_range_overflows(0xFFFFFFFCU, 5));
    assert(!memory_range_overflows(0xFFFFFFFCU, 4)); /* last byte 0xFFFFFFFF */
    assert(!memory_range_overflows(SRAM_BASE, 0x10000U));
}

static void test_overlap(void) {
    assert(memory_range_overlaps(0x1000U, 0x100U, 0x1050U, 0x100U));
    assert(memory_range_overlaps(0x1050U, 0x100U, 0x1000U, 0x100U));
    assert(!memory_range_overlaps(0x1000U, 0x100U, 0x1100U, 0x100U)); /* adjacent */
    assert(!memory_range_overlaps(0x1000U, 0, 0x1000U, 0x100U));
}

static void test_find_region(void) {
    const struct memory_region *r;
    r = find_region(s_test_map, TEST_MAP_N, DRAM_BASE + 0xFFCU, 4);
    assert(r != NULL && r->type == MEM_TYPE_DRAM);
    assert(find_region(s_test_map, TEST_MAP_N, 0x30000000U, 4) == NULL);
    assert(find_region(NULL, 0, SRAM_BASE, 4) == NULL);
    r = find_region(s_test_map, TEST_MAP_N, 0x20000000U, 1);
    assert(r != NULL && r->type == MEM_TYPE_MMIO);
}

int main(void) {
    test_contains_edges();
    test_overflow();
    test_overlap();
    test_find_region();
    printf("test_mem_regions: all cases passed\n");
    return 0;
}
