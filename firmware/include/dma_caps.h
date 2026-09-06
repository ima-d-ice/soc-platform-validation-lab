/* Generic DMA capability model (GENERAL CONCEPT).
 *
 * A DMA implementation supports an address-type matrix over a platform's
 * memory map, an alignment, a max transfer, and optional features. Pure
 * helpers implemented static-inline here. PLATFORM CONFIGURATION (e.g.
 * firmware/platforms/vlab/) supplies the concrete DmaCaps, the memory map,
 * and the DMA-capable peripheral endpoint table; CURRENT VLAB
 * IMPLEMENTATION enables RAM->RAM, RAM->Peripheral and Peripheral->RAM,
 * 4-byte aligned, 16KB max.
 *
 * Error split (mirrors soc_c DMA validation): invalid driver-API use
 * (bad length multiple, misaligned, unmapped/overflowing address) is
 * reported with the classic codes; mapped-but-unsupported endpoints,
 * directions, roles, or over-max lengths report DMA_ERR_UNSUPPORTED, i.e.
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

/* DMA-capable peripheral endpoint (GENERAL CONCEPT).
 *
 * A mapped MMIO region is NOT automatically a DMA endpoint. A platform
 * lists the peripheral FIFOs its DMA can actually stream, each anchored at
 * one FIFO register address with allowed roles:
 *   DMA_EP_SRC: may be a transfer source (Peripheral -> RAM)
 *   DMA_EP_DST: may be a transfer destination (RAM -> Peripheral)
 * Length/alignment/max-transfer are still validated separately, so the
 * entry carries no size: any validated length may stream through the FIFO.
 * A mapped MMIO address with no entry here is VALID but NOT DMA-capable
 * (reject with UNSUPPORTED, never ADDR). With no table installed
 * (NULL, 0), any mapped MMIO/peripheral region is a candidate endpoint
 * (legacy custom-map behavior); platforms that care install an allowlist.
 */
typedef enum {
    DMA_EP_SRC = (1 << 0),
    DMA_EP_DST = (1 << 1)
} dma_ep_role_t;

struct dma_periph_ep {
    const char *name; /* e.g. "uart-tx" */
    uint32_t fifo_addr; /* FIFO register address (must be word-aligned) */
    uint32_t roles;     /* DMA_EP_SRC and/or DMA_EP_DST */
};

/* Find the capable endpoint anchored at addr; NULL if none. Length is NOT
 * checked here (LEN/ALIGN/MAX validation owns it). */
static inline const struct dma_periph_ep *dma_periph_find(
    const struct dma_periph_ep *table, uint32_t n, uint32_t addr) {
    uint32_t i;
    if (table == NULL) return NULL;
    for (i = 0; i < n; i++) {
        if (table[i].fifo_addr == addr) return &table[i];
    }
    return NULL;
}

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
