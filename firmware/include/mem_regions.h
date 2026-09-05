/* Generic memory-region abstraction (GENERAL CONCEPT).
 *
 * A memory map is a table of regions; these helpers answer containment,
 * validity, overflow, and overlap for any platform's table. Pure functions
 * implemented static-inline here: no state, no backend, no device logic.
 * PLATFORM CONFIGURATION (e.g. firmware/platforms/vlab/) supplies the
 * actual table; CURRENT VLAB IMPLEMENTATION uses ROM/SRAM/MMIO entries.
 */
#ifndef VLAB_MEM_REGIONS_H
#define VLAB_MEM_REGIONS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Region types: general vocabulary; a platform uses the subset it has. */
typedef enum {
    MEM_TYPE_ROM = 0,
    MEM_TYPE_SRAM,
    MEM_TYPE_DRAM,
    MEM_TYPE_MMIO,
    MEM_TYPE_PERIPHERAL
} mem_type_t;

/* Permission bits. */
#define MEM_PERM_R (1U << 2)
#define MEM_PERM_W (1U << 1)
#define MEM_PERM_X (1U << 0)

struct memory_region {
    const char *name; /* routing key, e.g. "rom", "sram", "uart" */
    uint32_t base;
    uint32_t size;
    mem_type_t type;
    uint32_t perms;
};

static inline bool memory_region_contains(const struct memory_region *r,
                                          uint32_t addr, uint32_t len) {
    uint64_t end;
    if (r == NULL || len == 0) return false;
    end = (uint64_t)addr + (uint64_t)len;
    if (end > 0x100000000ULL) return false; /* wraps past 32-bit space */
    return addr >= r->base && end <= (uint64_t)r->base + (uint64_t)r->size;
}

static inline bool memory_range_valid(const struct memory_region *r,
                                      uint32_t addr, uint32_t len) {
    return len > 0 && memory_region_contains(r, addr, len);
}

static inline bool memory_range_overflows(uint32_t addr, uint32_t len) {
    /* uint32_t cannot be negative; overflow means end past 0xFFFFFFFF. */
    return (uint64_t)addr + (uint64_t)len > 0x100000000ULL;
}

static inline bool memory_range_overlaps(uint32_t a_base, uint32_t a_len,
                                         uint32_t b_base, uint32_t b_len) {
    uint64_t a_end, b_end;
    if (a_len == 0 || b_len == 0) return false;
    a_end = (uint64_t)a_base + (uint64_t)a_len;
    b_end = (uint64_t)b_base + (uint64_t)b_len;
    return (uint64_t)a_base < b_end && (uint64_t)b_base < a_end;
}

static inline const struct memory_region *find_region(
    const struct memory_region *table, uint32_t n, uint32_t addr,
    uint32_t len) {
    uint32_t i;
    if (table == NULL) return NULL;
    for (i = 0; i < n; i++) {
        if (memory_region_contains(&table[i], addr, len)) return &table[i];
    }
    return NULL;
}

#endif /* VLAB_MEM_REGIONS_H */
