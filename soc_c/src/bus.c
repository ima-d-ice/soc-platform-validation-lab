/* Bus: address decode from the platform region table.
 *
 * CPU ----[address]----> bus ----> which region owns it?
 *   ROM/SRAM images probe with word width (4); MMIO windows probe with
 *   single-byte width. Unmapped -> -1 (caller raises the bus error).
 */
#include "soc.h"

int soc_bus_route(const struct memory_region *regions, uint32_t n,
                  uint32_t addr) {
    uint32_t i;
    int first = -1;
    for (i = 0; i < n; i++) {
        if (memory_region_contains(&regions[i], addr, 4)) {
            first = (int)i;
            break;
        }
    }
    if (first == 0 || first == 1) return first;
    for (i = 0; i < n; i++) {
        if (memory_region_contains(&regions[i], addr, 1) && (int)i >= 2)
            return (int)i;
    }
    return -1;
}
