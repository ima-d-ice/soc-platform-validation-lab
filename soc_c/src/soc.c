#include "soc.h"

#include <string.h>

#include "platform/platform_vlab.h"

void soc_config_default(soc_config_t *cfg) {
    cfg->cpu_frequency_mhz = 100;
    cfg->uart_latency_ticks = 5;
    cfg->dma_latency_per_word_ticks = 1;
    cfg->dma_burst = 4;
}

static int soc_dma_reader_bridge(void *ctx, uint32_t addr, uint32_t len,
                                 uint8_t *out) {
    soc_t *s = (soc_t *)ctx;
    if (addr == SOC_UART_BASE + SOC_UART_RXDATA_OFF) {
        /* Peripheral source: drain the RX stream (short reads zero-pad). */
        soc_uart_dma_rx_drain(&s->uart, out, len);
        return SOC_OK;
    }
    return soc_mem_read_bytes(&s->sram, addr, len, out);
}

static int soc_dma_writer_bridge(void *ctx, uint32_t addr,
                                 const uint8_t *payload, uint32_t len) {
    soc_t *s = (soc_t *)ctx;
    if (addr == SOC_UART_BASE + SOC_UART_TXDATA_OFF) {
        /* Peripheral sink: stream into the TX FIFO (loopback feeds RX). */
        soc_uart_dma_tx_append(&s->uart, payload, len);
        return SOC_OK;
    }
    return soc_mem_write_bytes(&s->sram, addr, payload, len);
}

void soc_init(soc_t *s, const soc_config_t *cfg) {
    soc_config_t dflt;
    const struct memory_region *map;
    const struct dma_caps *caps;
    const struct dma_periph_ep *eps;
    uint32_t map_n = 0, eps_n = 0;
    if (!cfg) {
        soc_config_default(&dflt);
        cfg = &dflt;
    }
    s->config = *cfg;
    /* ONE platform table (firmware/platform/): map, caps, FIFOs. */
    map = vlab_memory_map(&map_n);
    caps = vlab_dma_caps();
    eps = vlab_dma_periph_eps(&eps_n);
    s->regions = map;
    s->n_regions = map_n;

    s->rom_backing = s->_rom_store;
    s->sram_backing = s->_sram_store;
    /* Platform entries 0/1 are ROM/SRAM (sizes fit the static stores). */
    soc_mem_init(&s->rom, map[0].base, map[0].size, 1, "ROM",
                 s->rom_backing);
    soc_mem_init(&s->sram, map[1].base, map[1].size, 0, "SRAM",
                 s->sram_backing);

    soc_perf_init(&s->perf);
    soc_intc_init(&s->intc, &s->perf);
    soc_uart_init(&s->uart, s->config.uart_latency_ticks, &s->perf,
                  &s->intc);
    soc_timer_init(&s->timer, &s->intc);
    soc_dma_init(&s->dma, s->config.dma_latency_per_word_ticks,
                 s->config.dma_burst, map, map_n, eps, eps_n, caps,
                 SOC_IRQ_DMA, &s->intc, &s->perf, soc_dma_reader_bridge,
                 soc_dma_writer_bridge, s);
    soc_cpu_init(&s->cpu, SOC_ROM_BASE, map[1].base + map[1].size);
    s->ticks = 0;
}

void soc_reset_peripherals(soc_t *s) {
    soc_uart_reset(&s->uart);
    soc_timer_reset(&s->timer);
    soc_dma_reset(&s->dma);
    soc_intc_reset(&s->intc);
}

/* Decode lives in the bus module; SoC integration calls it here. */
static int soc_route(soc_t *s, uint32_t addr) {
    return soc_bus_route(s->regions, s->n_regions, addr);
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
    /* SP = top of SRAM from the platform map (entry 1). */
    s->cpu.sram_top = s->regions[1].base + s->regions[1].size;
    s->cpu.sp = s->cpu.sram_top;
    soc_reset_peripherals(s);
    soc_perf_reset_counters(&s->perf);
    s->perf.enabled = 1;
    s->perf.ctrl = 0x1;
    if (rom_words && nwords > 0) {
        memset(s->rom_backing, 0, s->regions[0].size);
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
