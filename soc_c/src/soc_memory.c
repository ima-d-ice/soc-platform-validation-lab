#include "soc_memory.h"

#include <string.h>

void soc_mem_init(soc_mem_t *m, uint32_t base, uint32_t size, int readonly,
                  const char *name, uint8_t *backing) {
    m->base = base;
    m->size = size;
    m->readonly = readonly;
    m->name = name;
    m->data = backing;
    if (backing) memset(backing, 0, size);
}

int soc_mem_contains(const soc_mem_t *m, uint32_t addr, uint32_t len) {
    uint64_t end = (uint64_t)addr + (uint64_t)len;
    if (len == 0) return 0;
    if (end > 0x100000000ULL) return 0;
    return addr >= m->base && end <= (uint64_t)m->base + (uint64_t)m->size;
}

static int soc_mem_offset(const soc_mem_t *m, uint32_t addr, uint32_t len,
                          uint32_t *off) {
    uint64_t end = (uint64_t)addr + (uint64_t)len;
    if (len == 0) return SOC_ERR_BUS;
    if (end > 0x100000000ULL) return SOC_ERR_BUS;
    if (!(addr >= m->base && end <= (uint64_t)m->base + (uint64_t)m->size))
        return SOC_ERR_BUS;
    *off = addr - m->base;
    return SOC_OK;
}

int soc_mem_read_word(const soc_mem_t *m, uint32_t addr, uint32_t *out) {
    uint32_t off;
    if (addr % 4 != 0) return SOC_ERR_BUS;
    if (soc_mem_offset(m, addr, 4, &off) != SOC_OK) return SOC_ERR_BUS;
    *out = (uint32_t)m->data[off] | ((uint32_t)m->data[off + 1] << 8) |
           ((uint32_t)m->data[off + 2] << 16) |
           ((uint32_t)m->data[off + 3] << 24);
    return SOC_OK;
}

int soc_mem_write_word(soc_mem_t *m, uint32_t addr, uint32_t value) {
    uint32_t off;
    if (addr % 4 != 0) return SOC_ERR_BUS;
    if (m->readonly) return SOC_ERR_BUS;
    if (soc_mem_offset(m, addr, 4, &off) != SOC_OK) return SOC_ERR_BUS;
    m->data[off] = (uint8_t)(value & 0xFF);
    m->data[off + 1] = (uint8_t)((value >> 8) & 0xFF);
    m->data[off + 2] = (uint8_t)((value >> 16) & 0xFF);
    m->data[off + 3] = (uint8_t)((value >> 24) & 0xFF);
    return SOC_OK;
}

int soc_mem_read_bytes(const soc_mem_t *m, uint32_t addr, uint32_t len,
                       uint8_t *out) {
    uint32_t off;
    if (soc_mem_offset(m, addr, len, &off) != SOC_OK) return SOC_ERR_BUS;
    memcpy(out, &m->data[off], len);
    return SOC_OK;
}

int soc_mem_write_bytes(soc_mem_t *m, uint32_t addr, const uint8_t *payload,
                        uint32_t len) {
    uint32_t off;
    if (m->readonly) return SOC_ERR_BUS;
    if (soc_mem_offset(m, addr, len, &off) != SOC_OK) return SOC_ERR_BUS;
    memcpy(&m->data[off], payload, len);
    return SOC_OK;
}

int soc_mem_load_words(soc_mem_t *m, const uint32_t *words, uint32_t nwords) {
    uint32_t i;
    for (i = 0; i < nwords; i++) {
        uint32_t off = i * 4;
        uint32_t w;
        if (off + 4 > m->size) return SOC_ERR_BUS;
        w = words[i];
        m->data[off] = (uint8_t)(w & 0xFF);
        m->data[off + 1] = (uint8_t)((w >> 8) & 0xFF);
        m->data[off + 2] = (uint8_t)((w >> 16) & 0xFF);
        m->data[off + 3] = (uint8_t)((w >> 24) & 0xFF);
    }
    return SOC_OK;
}

void soc_mem_zero(soc_mem_t *m) {
    if (m->data) memset(m->data, 0, m->size);
}
