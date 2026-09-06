#include "soc.h"

void soc_cpu_init(soc_cpu_t *c, uint32_t rom_base, uint32_t sram_top) {
    c->rom_base = rom_base;
    c->sram_top = sram_top;
    c->pc = rom_base;
    c->sp = sram_top;
    c->running = 0;
    c->boot_ticks = 0;
}

void soc_cpu_reset(soc_cpu_t *c) {
    c->pc = c->rom_base;
    c->sp = c->sram_top;
    c->running = 0;
    c->boot_ticks = 0;
}

void soc_cpu_enter_main(soc_cpu_t *c) { c->running = 1; }
