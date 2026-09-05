/* Generic DMA capability model (GENERAL CONCEPT).
 *
 * A DMA implementation supports an address-type matrix over a platform's
 * memory map, an alignment, a max transfer, and optional features. Pure
 * helpers implemented static-inline here. PLATFORM CONFIGURATION (e.g.
 * firmware/platforms/vlab/) supplies the concrete DmaCaps; CURRENT VLAB
 * IMPLEMENTATION is SRAM-only, 4-byte aligned, 16KB max.
 *
 * Error split (mirrors soc/dma_caps.py): invalid driver-API use
 * (bad length multiple, misaligned, unmapped/overflowing address) is
 * reported with the classic codes; mapped-but-unsupported endpoints,
 * directions, or over-max lengths report DMA_ERR_UNSUPPORTED, i.e.
 * "unsupported by platform" rather than "invalid".
 */
#ifndef VLAB_DMA_CAPS_H
#define VLAB_DMA_CAPS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "mem_regions.h"

/* Endpoint address types from the DMA's point of view. */
typedef enum {
    DMA_ADDR_MEM = 0,
    DMA_ADDR_PERIPHERAL,
    DMA_ADDR_DEVICE
} dma_addr_type_t;

/* Register-level error code for platform-unsupported transfers
 * (additive; classic codes 0..3 keep their frozen meanings). */
#define DMA_HW_ERR_UNSUPPORTED 4U

struct dma_caps {
    uint32_t alignment;      /* required endpoint/length granularity */
    uint32_t max_transfer;   /* bytes; 0 = unlimited */
    bool supports_ram_to_ram;
    bool supports_mem_to_periph;
    bool supports_periph_to_mem;
    bool supports_interrupts;
    bool supports_cancel;
};

/* Classify one endpoint; returns -1 when unmapped/overflowing. */
static inline int dma_endpoint_type(const struct memory_region *table,
                                    uint32_t n, uint32_t addr, uint32_t len) {
    const struct memory_region *r = find_region(table, n, addr, len);
    if (r == NULL) return -1;
    if (r->type == MEM_TYPE_SRAM || r->type == MEM_TYPE_DRAM)
        return (int)DMA_ADDR_MEM;
    if (r->type == MEM_TYPE_MMIO || r->type == MEM_TYPE_PERIPHERAL)
        return (int)DMA_ADDR_PERIPHERAL;
    return (int)DMA_ADDR_DEVICE;
}

static inline bool dma_address_valid(const struct memory_region *table,
                                     uint32_t n,
                                     const struct dma_caps *caps,
                                     uint32_t addr, uint32_t len, int type) {
    int actual;
    if (caps == NULL || len == 0) return false;
    if (caps->alignment > 1 &&
        (addr % caps->alignment != 0 || len % caps->alignment != 0))
        return false;
    actual = dma_endpoint_type(table, n, addr, len);
    if (actual < 0) return false;
    if (type == (int)DMA_ADDR_MEM) return actual == (int)DMA_ADDR_MEM;
    if (type == (int)DMA_ADDR_PERIPHERAL)
        return actual == (int)DMA_ADDR_PERIPHERAL || actual == (int)DMA_ADDR_DEVICE;
    if (type == (int)DMA_ADDR_DEVICE) return actual == (int)DMA_ADDR_DEVICE;
    return false;
}

static inline bool dma_direction_supported(const struct dma_caps *caps,
                                           int src_type, int dst_type) {
    if (caps == NULL) return false;
    if (src_type == (int)DMA_ADDR_MEM && dst_type == (int)DMA_ADDR_MEM)
        return caps->supports_ram_to_ram;
    if (src_type == (int)DMA_ADDR_MEM &&
        (dst_type == (int)DMA_ADDR_PERIPHERAL || dst_type == (int)DMA_ADDR_DEVICE))
        return caps->supports_mem_to_periph;
    if ((src_type == (int)DMA_ADDR_PERIPHERAL || src_type == (int)DMA_ADDR_DEVICE) &&
        dst_type == (int)DMA_ADDR_MEM)
        return caps->supports_periph_to_mem;
    return false;
}

#endif /* VLAB_DMA_CAPS_H */
