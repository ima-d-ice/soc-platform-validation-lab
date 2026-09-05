/* Top-level virtual SoC: bus decode + tick stepping + boot.
 * Mirrors soc/soc.py. Deterministic tick-stepped model.
 *
 * Memory map (VLAB, from configs/regs.yaml):
 *   ROM   0x00000000  size cfg  r-x
 *   SRAM  0x10000000  size cfg  rw-
 *   UART  0x20000000  4K
 *   TIMER 0x20001000  4K
 *   DMA   0x20002000  4K
 *   INTC  0x20003000  4K
 *   PERF  0x20004000  4K
 */
#ifndef SOC_C_SOC_H
#define SOC_C_SOC_H

#include <stdint.h>

#include "soc_bus.h"
#include "soc_cpu.h"
#include "soc_dma.h"
#include "soc_intc.h"
#include "soc_memory.h"
#include "soc_perf.h"
#include "soc_timer.h"
#include "soc_uart.h"

#define SOC_ROM_BASE 0x00000000U
#define SOC_SRAM_BASE 0x10000000U
#define SOC_UART_BASE 0x20000000U
#define SOC_TIMER_BASE 0x20001000U
#define SOC_DMA_BASE 0x20002000U
#define SOC_INTC_BASE 0x20003000U
#define SOC_PERF_BASE 0x20004000U
#define SOC_REGION_SIZE 0x1000U
#define SOC_BOOT_TICKS 5

#define SOC_ROM_SIZE_DEFAULT 16384U
#define SOC_SRAM_SIZE_DEFAULT 65536U
#define SOC_MAX_ROM_SIZE 65536U
#define SOC_MAX_SRAM_SIZE 262144U

typedef struct {
    uint32_t rom_size_bytes;
    uint32_t sram_size_bytes;
    uint32_t cpu_frequency_mhz;
    uint32_t uart_latency_ticks;
    uint32_t dma_latency_per_word_ticks;
    uint32_t dma_burst;
    uint32_t dma_max_transfer_bytes;
    uint32_t timer_tick_ticks; /* reserved, MVP always 1 */
} soc_config_t;

void soc_config_default(soc_config_t *cfg);

typedef struct soc_t {
    soc_config_t config;
    soc_mem_t rom;
    soc_mem_t sram;
    uint8_t *rom_backing;
    uint8_t *sram_backing;
    /* Owned backing store (max sizes, sliced by config). */
    uint8_t _rom_store[SOC_MAX_ROM_SIZE];
    uint8_t _sram_store[SOC_MAX_SRAM_SIZE];
    soc_region_t regions[7];
    soc_perf_t perf;
    soc_intc_t intc;
    soc_uart_t uart;
    soc_timer_t timer;
    soc_dma_t dma;
    soc_cpu_t cpu;
    uint32_t ticks;
} soc_t;

void soc_init(soc_t *s, const soc_config_t *cfg);
void soc_reset_peripherals(soc_t *s);

/* MMIO. soc_read: SOC_OK or SOC_ERR_BUS. soc_write: SOC_OK, SOC_ERR_BUS,
 * or peripheral status (e.g. SOC_UART_ERR_DISABLED=-1 for UART TX). */
int soc_read(soc_t *s, uint32_t addr, uint32_t *out);
int soc_write(soc_t *s, uint32_t addr, uint32_t value);

void soc_step(soc_t *s, uint32_t n);

/* Step until *pred(ctx) true; returns ticks elapsed, or -1 on timeout. */
typedef int (*soc_pred_t)(void *ctx);
int soc_run_until(soc_t *s, soc_pred_t pred, void *ctx, uint32_t max_ticks);

typedef struct {
    uint32_t boot_ticks;
    uint32_t cpu_frequency_mhz;
    uint32_t boot_ns;
} soc_boot_info_t;

soc_boot_info_t soc_boot(soc_t *s, const uint32_t *rom_words,
                         uint32_t nwords);

/* SRAM helpers for tests. */
int soc_sram_write_word(soc_t *s, uint32_t addr, uint32_t value);
int soc_sram_read_word(soc_t *s, uint32_t addr, uint32_t *out);

#endif /* SOC_C_SOC_H */
