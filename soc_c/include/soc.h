/* Virtual SoC model: one header for all modules.
 *
 * Map/caps vocabulary (memory_region, dma_caps, endpoint helpers) is the
 * single shared source in firmware/include. This header adds the model
 * state: CPU, bus, memory, and the UART/Timer/INTC/DMA/PERF peripherals.
 */
#ifndef SOC_C_SOC_H
#define SOC_C_SOC_H

#include <stddef.h>
#include <stdint.h>

#include "dma_caps.h"
#include "mem_regions.h"

/* ---- bus: error codes + address decode ---- */
#define SOC_OK 0
#define SOC_ERR_BUS (-100)

/* Route addr to a region index (word-width probe for ROM/SRAM images,
 * single-byte probe for MMIO windows), or -1 when unmapped. */
int soc_bus_route(const struct memory_region *regions, uint32_t n,
                  uint32_t addr);

/* ---- cpu: one component of the SoC (CPU != SoC) ----
 * Minimal state: reset/halt/run, PC/SP. The CPU does not decode
 * instructions here; it marks where execution is (ROM) and where the
 * stack lives (SRAM top). */
typedef struct {
    uint32_t rom_base;
    uint32_t sram_top;
    uint32_t pc;
    uint32_t sp;
    int running;
    uint32_t boot_ticks;
} soc_cpu_t;

void soc_cpu_init(soc_cpu_t *c, uint32_t rom_base, uint32_t sram_top);
void soc_cpu_reset(soc_cpu_t *c);
void soc_cpu_enter_main(soc_cpu_t *c);

/* ---- memory: byte-addressable backing store ----
 * One address = one byte = one uint8_t. Words are 4 consecutive bytes
 * (little-endian); word access requires addr % 4 == 0. ROM enforces
 * read-only at run time. No heap: the caller provides the buffer. */
typedef struct {
    uint32_t base;
    uint32_t size;
    int readonly;
    const char *name;
    uint8_t *data;
} soc_mem_t;

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

/* ---- perf: real model counters (never synthesised) ---- */
#define SOC_PERF_CYCLES_OFF 0x00
#define SOC_PERF_MEM_ACC_OFF 0x04
#define SOC_PERF_DMA_BYTES_OFF 0x08
#define SOC_PERF_IRQ_COUNT_OFF 0x0C
#define SOC_PERF_STALLS_OFF 0x10
#define SOC_PERF_CTRL_OFF 0x14

#define SOC_PERF_CTRL_ENABLE (1U << 0)
#define SOC_PERF_CTRL_RESET (1U << 1)

typedef struct soc_perf_t {
    uint32_t cycles;
    uint32_t mem_acc;
    uint32_t dma_bytes;
    uint32_t irq_count;
    uint32_t stalls;
    int enabled;
    uint32_t ctrl;
} soc_perf_t;

void soc_perf_init(soc_perf_t *p);
void soc_perf_reset_counters(soc_perf_t *p);
void soc_perf_tick(soc_perf_t *p);
void soc_perf_count_mem(soc_perf_t *p);
void soc_perf_count_stall(soc_perf_t *p, uint32_t n);
void soc_perf_count_dma(soc_perf_t *p, uint32_t nbytes);
void soc_perf_count_irq(soc_perf_t *p);
int soc_perf_read(soc_perf_t *p, uint32_t offset, uint32_t *out);
int soc_perf_write(soc_perf_t *p, uint32_t offset, uint32_t value);

/* ---- intc: enable/pending/active + read-to-ack ----
 * Fixed priority: TIMER(1) > DMA(2) > UART(0). Non-preemptive, queued.
 * Raises coalesce; ACK moves PENDING->ACTIVE and counts one IRQ. */
#define SOC_INTC_ENABLE_OFF 0x00
#define SOC_INTC_PENDING_OFF 0x04
#define SOC_INTC_ACK_OFF 0x08
#define SOC_INTC_CLEAR_OFF 0x0C
#define SOC_INTC_ACTIVE_OFF 0x10

#define SOC_IRQ_UART 0
#define SOC_IRQ_TIMER 1
#define SOC_IRQ_DMA 2
#define SOC_IRQ_NONE 0xFFFFFFFFU
#define SOC_N_LINES 3

typedef struct soc_intc_t {
    uint32_t enable;
    uint32_t pending;
    uint32_t active;
    struct soc_perf_t *perf;
} soc_intc_t;

void soc_intc_init(soc_intc_t *ic, struct soc_perf_t *perf);
void soc_intc_reset(soc_intc_t *ic);
void soc_intc_raise(soc_intc_t *ic, int line);
int soc_intc_read(soc_intc_t *ic, uint32_t offset, uint32_t *out);
int soc_intc_write(soc_intc_t *ic, uint32_t offset, uint32_t value);

/* ---- uart: loopback + busy latency + RX completion IRQ (line 0) ---- */
#define SOC_UART_TXDATA_OFF 0x00
#define SOC_UART_RXDATA_OFF 0x04
#define SOC_UART_STATUS_OFF 0x08
#define SOC_UART_CTRL_OFF 0x0C
#define SOC_UART_BAUDDIV_OFF 0x10

#define SOC_UART_STATUS_TX_BUSY (1U << 0)
#define SOC_UART_STATUS_TX_EMPTY (1U << 1)
#define SOC_UART_STATUS_RX_VALID (1U << 2)
#define SOC_UART_CTRL_ENABLE (1U << 0)

#define SOC_UART_ERR_DISABLED (-1)
#define SOC_UART_IRQ_LINE 0

/* DMA-visible stream FIFOs (model depth, not registers). uart-tx is the
 * DMA sink, uart-rx the DMA source. CPU single-byte loopback is unchanged;
 * completions also feed the streams so both paths see looped-back bytes. */
#define SOC_UART_DMA_FIFO_SIZE 16384U

typedef struct soc_uart_t {
    uint32_t latency_ticks;
    struct soc_perf_t *perf;
    struct soc_intc_t *intc;
    uint32_t ctrl;
    uint32_t bauddiv;
    uint32_t txdata;
    uint32_t rxdata;
    int32_t busy;
    int rx_valid;
    int fault_stuck_busy;
    uint8_t dma_tx_fifo[SOC_UART_DMA_FIFO_SIZE];
    uint32_t dma_tx_len;
    uint8_t dma_rx_fifo[SOC_UART_DMA_FIFO_SIZE];
    uint32_t dma_rx_len;
} soc_uart_t;

void soc_uart_init(soc_uart_t *u, uint32_t latency_ticks,
                   struct soc_perf_t *perf, struct soc_intc_t *intc);
void soc_uart_reset(soc_uart_t *u);
int soc_uart_read(soc_uart_t *u, uint32_t offset, uint32_t *out);
/* Returns 0 ok, SOC_UART_ERR_DISABLED if TX while disabled. */
int soc_uart_write(soc_uart_t *u, uint32_t offset, uint32_t value);
void soc_uart_step(soc_uart_t *u);
/* Appends saturate at capacity; short RX drains zero-pad. */
void soc_uart_dma_tx_append(soc_uart_t *u, const uint8_t *payload,
                            uint32_t len);
void soc_uart_dma_rx_drain(soc_uart_t *u, uint8_t *out, uint32_t len);

/* ---- timer: one-shot / periodic countdown + IRQ (line 1) ---- */
#define SOC_TIMER_CTRL_OFF 0x00
#define SOC_TIMER_LOAD_OFF 0x04
#define SOC_TIMER_VALUE_OFF 0x08
#define SOC_TIMER_IRQ_STATUS_OFF 0x0C
#define SOC_TIMER_IRQ_CLEAR_OFF 0x10

#define SOC_TIMER_CTRL_ENABLE (1U << 0)
#define SOC_TIMER_CTRL_PERIODIC (1U << 1)
#define SOC_TIMER_CTRL_IRQ_ENABLE (1U << 2)
#define SOC_TIMER_IRQ_FIRED (1U << 0)

#define SOC_TIMER_IRQ_LINE 1

typedef struct soc_timer_t {
    struct soc_intc_t *intc;
    uint32_t ctrl;
    uint32_t load;
    uint32_t value;
    uint32_t irq_status;
} soc_timer_t;

void soc_timer_init(soc_timer_t *t, struct soc_intc_t *intc);
void soc_timer_reset(soc_timer_t *t);
int soc_timer_read(soc_timer_t *t, uint32_t offset, uint32_t *out);
int soc_timer_write(soc_timer_t *t, uint32_t offset, uint32_t value);
void soc_timer_step(soc_timer_t *t);

/* ---- dma: burst engine + completion/error IRQ (line 2) ----
 * Single channel. CTRL.START auto-clears, STATUS sticky until next START
 * or IRQ_CLEAR, memmove semantics for overlap. Burst size is config-only.
 * Timing: ticks = words*latency_per_word + (bursts-1), bursts=ceil(w/burst).
 * Validation (BUSY/LEN/ALIGN/MAX/ADDR/DIRECTION) mirrors the firmware
 * driver; error codes match the register map. */
#define SOC_DMA_SRC_OFF 0x00
#define SOC_DMA_DST_OFF 0x04
#define SOC_DMA_LEN_OFF 0x08
#define SOC_DMA_CTRL_OFF 0x0C
#define SOC_DMA_STATUS_OFF 0x10
#define SOC_DMA_IRQ_CLEAR_OFF 0x14
#define SOC_DMA_ERR_CODE_OFF 0x18

#define SOC_DMA_CTRL_START (1U << 0)
#define SOC_DMA_CTRL_IRQ_ENABLE (1U << 1)

#define SOC_DMA_STATUS_BUSY (1U << 0)
#define SOC_DMA_STATUS_DONE (1U << 1)
#define SOC_DMA_STATUS_ERROR (1U << 2)

#define SOC_DMA_ERR_NONE 0
#define SOC_DMA_ERR_ADDR 1
#define SOC_DMA_ERR_ALIGN 2
#define SOC_DMA_ERR_LEN 3
#define SOC_DMA_ERR_UNSUPPORTED 4

#define SOC_DMA_IRQ_LINE 2

typedef struct soc_dma_t soc_dma_t;
/* Memory/peripheral bridge without import cycles. SOC_OK/SOC_ERR_BUS. */
typedef int (*soc_dma_reader_t)(void *ctx, uint32_t addr, uint32_t len,
                                uint8_t *out);
typedef int (*soc_dma_writer_t)(void *ctx, uint32_t addr,
                                const uint8_t *payload, uint32_t len);

struct soc_dma_t {
    uint32_t latency_per_word;
    uint32_t burst;
    const struct memory_region *regions;
    uint32_t n_regions;
    const struct dma_periph_ep *periph_eps;
    uint32_t n_periph_eps;
    struct dma_caps caps;
    int irq_line;
    struct soc_intc_t *intc;
    struct soc_perf_t *perf;
    soc_dma_reader_t reader;
    soc_dma_writer_t writer;
    void *mem_ctx;
    uint32_t src;
    uint32_t dst;
    uint32_t length;
    uint32_t ctrl;
    int busy;
    int done;
    int error;
    uint32_t err_code;
    int32_t remaining;
    int irq_enable_latched;
    int fault_stuck_busy;
};

void soc_dma_init(soc_dma_t *d, uint32_t latency_per_word, uint32_t burst,
                  const struct memory_region *regions, uint32_t n_regions,
                  const struct dma_periph_ep *periph_eps,
                  uint32_t n_periph_eps, const struct dma_caps *caps,
                  int irq_line, struct soc_intc_t *intc,
                  struct soc_perf_t *perf, soc_dma_reader_t reader,
                  soc_dma_writer_t writer, void *mem_ctx);
void soc_dma_reset(soc_dma_t *d);
int soc_dma_read(soc_dma_t *d, uint32_t offset, uint32_t *out);
int soc_dma_write(soc_dma_t *d, uint32_t offset, uint32_t value);
void soc_dma_step(soc_dma_t *d);

/* ---- top: integration, tick, boot ----
 * Map/caps/FIFOs come from the single platform table (firmware/platform/);
 * values in docs/soc-spec.md:
 *   ROM 0x00000000 16K r-x / SRAM 0x10000000 64K rw- /
 *   UART 0x20000000 / TIMER 0x20001000 / DMA 0x20002000 /
 *   INTC 0x20003000 / PERF 0x20004000 (4K each) */
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
    uint32_t cpu_frequency_mhz; /* informational: ticks->ns for reporting */
    uint32_t uart_latency_ticks;
    uint32_t dma_latency_per_word_ticks;
    uint32_t dma_burst; /* words per burst, config-only (no BURST reg) */
} soc_config_t;

void soc_config_default(soc_config_t *cfg);

typedef struct soc_t {
    soc_config_t config;
    soc_mem_t rom;
    soc_mem_t sram;
    uint8_t *rom_backing;
    uint8_t *sram_backing;
    /* Owned backing store (platform map sizes must fit). */
    uint8_t _rom_store[SOC_MAX_ROM_SIZE];
    uint8_t _sram_store[SOC_MAX_SRAM_SIZE];
    /* Platform-owned map (vlab_memory_map); not copied, not owned. */
    const struct memory_region *regions;
    uint32_t n_regions;
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
