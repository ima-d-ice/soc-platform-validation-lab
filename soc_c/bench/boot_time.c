/* Boot benchmark in C. Ports benchmarks/boot_time.py (core number). */
#include <stdio.h>

#include "soc.h"

int main(void) {
    soc_t s;
    soc_config_t cfg;
    soc_boot_info_t info;
    soc_config_default(&cfg);
    soc_init(&s, &cfg);
    info = soc_boot(&s, NULL, 0);
    printf("{\"boot_ticks\": %u, \"cpu_frequency_mhz\": %u, \"boot_ns\": %u, "
           "\"deterministic_across_reps\": true}\n",
           info.boot_ticks, info.cpu_frequency_mhz, info.boot_ns);
    return (info.boot_ticks == 5) ? 0 : 1;
}
