/* Minimal CPU model: reset/halt/run state, PC/SP, tick accounting.
 * Mirrors soc/cpu/__init__.py.
 */
#ifndef SOC_C_CPU_H
#define SOC_C_CPU_H

#include <stdint.h>

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

#endif /* SOC_C_CPU_H */
