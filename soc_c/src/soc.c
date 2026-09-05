#include "soc.h"

#include <string.h>

void soc_config_default(soc_config_t *cfg) {
    cfg->rom_size_bytes = SOC_ROM_SIZE_DEFAULT;
    cfg->sram_size_bytes = SOC_SRAM_SIZE_DEFAULT;
    cfg->cpu_frequency_mhz = 100;
    cfg->uart_latency_ticks = 5;
    cfg->dma_latency_per_word_ticks = 1;
    cfg->dma_burst = 4;
    cfg->dma_max_transfer_bytes = 16384;
    cfg->timer_tick_ticks = 1;
}

static int soc_dma_reader_bridge(void *ctx, uint32_t addr, uint32_t len,
                                 uint8_t *out) {
    soc_t *s = (soc_t *)ctx;
    return soc_mem_read_bytes(&s->sram, addr, len, out);
}

static int soc_dma_writer_bridge(void *ctx, uint32_t addr,
                                 const uint8_t *payload, uint32_t len) {
    soc_t *s = (soc_t *)ctx;
    return soc_mem_write_bytes(&s->sram, addr, payload, len);
}

void soc_init(soc_t *s, const soc_config_t *cfg) {
    soc_config_t dflt;
    soc_dma_caps_t caps;
    if (!cfg) {
        soc_config_default(&dflt);
        cfg = &dflt;
    }
    s->config = *cfg;
    if (s->config.rom_size_bytes > SOC_MAX_ROM_SIZE)
        s->config.rom_size_bytes = SOC_MAX_ROM_SIZE;
    if (s->config.sram_size_bytes > SOC_MAX_SRAM_SIZE)
        s->config.sram_size_bytes = SOC_MAX_SRAM_SIZE;

    s->rom_backing = s->_rom_store;
    s->sram_backing = s->_sram_store;
    soc_mem_init(&s->rom, SOC_ROM_BASE, s->config.rom_size_bytes, 1, "ROM",
                 s->rom_backing);
    soc_mem_init(&s->sram, SOC_SRAM_BASE, s->config.sram_size_bytes, 0,
                 "SRAM", s->sram_backing);

    s->regions[0].name = "rom";
    s->regions[0].base = SOC_ROM_BASE;
    s->regions[0].size = s->config.rom_size_bytes;
    s->regions[0].type = SOC_RTYPE_ROM;
    s->regions[1].name = "sram";
    s->regions[1].base = SOC_SRAM_BASE;
    s->regions[1].size = s->config.sram_size_bytes;
    s->regions[1].type = SOC_RTYPE_SRAM;
    s->regions[2].name = "uart";
    s->regions[2].base = SOC_UART_BASE;
    s->regions[2].size = SOC_REGION_SIZE;
    s->regions[2].type = SOC_RTYPE_MMIO;
    s->regions[3].name = "timer";
    s->regions[3].base = SOC_TIMER_BASE;
    s->regions[3].size = SOC_REGION_SIZE;
    s->regions[3].type = SOC_RTYPE_MMIO;
    s->regions[4].name = "dma";
    s->regions[4].base = SOC_DMA_BASE;
    s->regions[4].size = SOC_REGION_SIZE;
    s->regions[4].type = SOC_RTYPE_MMIO;
    s->regions[5].name = "intc";
    s->regions[5].base = SOC_INTC_BASE;
    s->regions[5].size = SOC_REGION_SIZE;
    s->regions[5].type = SOC_RTYPE_MMIO;
    s->regions[6].name = "perf";
    s->regions[6].base = SOC_PERF_BASE;
    s->regions[6].size = SOC_REGION_SIZE;
    s->regions[6].type = SOC_RTYPE_MMIO;

    soc_perf_init(&s->perf);
    soc_intc_init(&s->intc, &s->perf);
    soc_uart_init(&s->uart, s->config.uart_latency_ticks, &s->perf,
                  &s->intc);
    soc_timer_init(&s->timer, &s->intc);
    caps.alignment = 4;
    caps.max_transfer = s->config.dma_max_transfer_bytes;
    caps.supports_ram_to_ram = 1;
    caps.supports_mem_to_periph = 0;
    caps.supports_periph_to_mem = 0;
    soc_dma_init(&s->dma, SOC_SRAM_BASE, s->config.sram_size_bytes,
                 s->config.dma_latency_per_word_ticks, s->config.dma_burst,
                 s->regions, 7, &caps, SOC_IRQ_DMA, &s->intc, &s->perf,
                 soc_dma_reader_bridge, soc_dma_writer_bridge, s);
    soc_cpu_init(&s->cpu, SOC_ROM_BASE,
                 SOC_SRAM_BASE + s->config.sram_size_bytes);
    s->ticks = 0;
}

void soc_reset_peripherals(soc_t *s) {
    soc_uart_reset(&s->uart);
    soc_timer_reset(&s->timer);
    soc_dma_reset(&s->dma);
    soc_intc_reset(&s->intc);
}

static int soc_region_contains_addr(const soc_region_t *r, uint32_t addr,
                                    uint32_t len) {
    uint64_t end;
    if (!r || len == 0) return 0;
    end = (uint64_t)addr + (uint64_t)len;
    if (end > 0x100000000ULL) return 0;
    return addr >= r->base && end <= (uint64_t)r->base + (uint64_t)r->size;
}

/* Returns region index 0..6, or -1. */
static int soc_find_region_idx(soc_t *s, uint32_t addr, uint32_t len) {
    int i;
    for (i = 0; i < 7; i++) {
        if (soc_region_contains_addr(&s->regions[i], addr, len)) return i;
    }
    return -1;
}

/* Same widths as Python: word accesses for ROM/SRAM, byte presence for MMIO. */
static int soc_route(soc_t *s, uint32_t addr) {
    int idx = soc_find_region_idx(s, addr, 4);
    if (idx == 0 || idx == 1) return idx;
    idx = soc_find_region_idx(s, addr, 1);
    if (idx >= 2) return idx;
    return -1;
}

int soc_read(soc_t *s, uint32_t addr, uint32_t *out) {
    int kind, rc;
    if (addr % 4 != 0) {
        soc_perf_count_stall(&s->perf, 1);
        return SOC_ERR_BUS;
    }
    soc_perf_count_mem(&s->perf);
    kind = soc_route(s, addr);
    switch (kind) {
        case 0: rc = soc_mem_read_word(&s->rom, addr, out); break;
        case 1: rc = soc_mem_read_word(&s->sram, addr, out); break;
        case 2: rc = soc_uart_read(&s->uart, addr - SOC_UART_BASE, out); break;
        case 3: rc = soc_timer_read(&s->timer, addr - SOC_TIMER_BASE, out); break;
        case 4: rc = soc_dma_read(&s->dma, addr - SOC_DMA_BASE, out); break;
        case 5: rc = soc_intc_read(&s->intc, addr - SOC_INTC_BASE, out); break;
        case 6: rc = soc_perf_read(&s->perf, addr - SOC_PERF_BASE, out); break;
        default:
            soc_perf_count_stall(&s->perf, 1);
            return SOC_ERR_BUS;
    }
    if (rc != SOC_OK) {
        soc_perf_count_stall(&s->perf, 1);
        return SOC_ERR_BUS;
    }
    return SOC_OK;
}

int soc_write(soc_t *s, uint32_t addr, uint32_t value) {
    int kind, rc;
    if (addr % 4 != 0) {
        soc_perf_count_stall(&s->perf, 1);
        return SOC_ERR_BUS;
    }
    soc_perf_count_mem(&s->perf);
    kind = soc_route(s, addr);
    switch (kind) {
        case 0: rc = soc_mem_write_word(&s->rom, addr, value); break;
        case 1: rc = soc_mem_write_word(&s->sram, addr, value); break;
        case 2:
            rc = soc_uart_write(&s->uart, addr - SOC_UART_BASE, value);
            if (rc == SOC_UART_ERR_DISABLED) return rc;
            break;
        case 3: rc = soc_timer_write(&s->timer, addr - SOC_TIMER_BASE, value); break;
        case 4: rc = soc_dma_write(&s->dma, addr - SOC_DMA_BASE, value); break;
        case 5: rc = soc_intc_write(&s->intc, addr - SOC_INTC_BASE, value); break;
        case 6: rc = soc_perf_write(&s->perf, addr - SOC_PERF_BASE, value); break;
        default:
            soc_perf_count_stall(&s->perf, 1);
            return SOC_ERR_BUS;
    }
    if (rc != SOC_OK) {
        /* UART disabled (-1) passes through; bus errors count a stall. */
        if (rc == SOC_ERR_BUS) soc_perf_count_stall(&s->perf, 1);
        return rc;
    }
    return SOC_OK;
}

void soc_step(soc_t *s, uint32_t n) {
    uint32_t i;
    for (i = 0; i < n; i++) {
        s->ticks++;
        soc_perf_tick(&s->perf);
        soc_uart_step(&s->uart);
        soc_timer_step(&s->timer);
        soc_dma_step(&s->dma);
    }
}

int soc_run_until(soc_t *s, soc_pred_t pred, void *ctx, uint32_t max_ticks) {
    uint32_t elapsed = 0;
    while (elapsed < max_ticks) {
        if (pred && pred(ctx)) return (int)elapsed;
        soc_step(s, 1);
        elapsed++;
    }
    if (pred && pred(ctx)) return (int)elapsed;
    return -1;
}

soc_boot_info_t soc_boot(soc_t *s, const uint32_t *rom_words,
                         uint32_t nwords) {
    soc_boot_info_t info;
    s->ticks = 0;
    soc_cpu_reset(&s->cpu);
    /* Re-point SP in case config changed (matches Python SoC boot). */
    s->cpu.sram_top = SOC_SRAM_BASE + s->config.sram_size_bytes;
    s->cpu.sp = s->cpu.sram_top;
    soc_reset_peripherals(s);
    soc_perf_reset_counters(&s->perf);
    s->perf.enabled = 1;
    s->perf.ctrl = 0x1;
    if (rom_words && nwords > 0) {
        memset(s->rom_backing, 0, s->config.rom_size_bytes);
        soc_mem_load_words(&s->rom, rom_words, nwords);
    }
    soc_mem_zero(&s->sram);
    soc_step(s, SOC_BOOT_TICKS);
    soc_cpu_enter_main(&s->cpu);
    info.boot_ticks = s->ticks;
    info.cpu_frequency_mhz = s->config.cpu_frequency_mhz
                                 ? s->config.cpu_frequency_mhz
                                 : 100;
    info.boot_ns = (uint32_t)(s->ticks * 1000 / info.cpu_frequency_mhz);
    return info;
}

int soc_sram_write_word(soc_t *s, uint32_t addr, uint32_t value) {
    return soc_write(s, addr, value);
}

int soc_sram_read_word(soc_t *s, uint32_t addr, uint32_t *out) {
    return soc_read(s, addr, out);
}
