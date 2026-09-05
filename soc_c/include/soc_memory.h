/* Byte-addressable backing store + word helpers.
 * Mirrors soc/memory SimpleMemory. ROM enforces read-only at run time.
 */
#ifndef SOC_C_MEMORY_H
#define SOC_C_MEMORY_H

#include <stddef.h>
#include <stdint.h>

#include "soc_bus.h"

typedef struct {
    uint32_t base;
    uint32_t size;
    int readonly;
    const char *name;
    uint8_t *data;
} soc_mem_t;

/* Caller provides backing buffer of `size` bytes (allows static alloc). */
void soc_mem_init(soc_mem_t *m, uint32_t base, uint32_t size, int readonly,
                  const char *name, uint8_t *backing);
int soc_mem_contains(const soc_mem_t *m, uint32_t addr, uint32_t len);
int soc_mem_read_word(const soc_mem_t *m, uint32_t addr, uint32_t *out);
int soc_mem_write_word(soc_mem_t *m, uint32_t addr, uint32_t value);
int soc_mem_read_bytes(const soc_mem_t *m, uint32_t addr, uint32_t len,
                       uint8_t *out);
int soc_mem_write_bytes(soc_mem_t *m, uint32_t addr, const uint8_t *payload,
                        uint32_t len);
int soc_mem_load_words(soc_mem_t *m, const uint32_t *words, uint32_t nwords);
void soc_mem_zero(soc_mem_t *m);

#endif /* SOC_C_MEMORY_H */
