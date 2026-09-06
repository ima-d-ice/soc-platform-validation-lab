/* Minimal application: platform bring-up, UART hello, timer, metrics.
 *
 * main() -> platform_init() -> driver setup -> work. Time only advances
 * when the model steps, so every blocking wait pairs driver polls with
 * explicit soc_host_step() calls (a main loop / tick hook would do the
 * same on silicon-backed firmware).
 */
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "host_bridge.h"
#include "soc_regs.h"

#define UART_LATENCY_STEPS 5U

int main(void) {
    const char *msg = "hello vlab-soc";
    const char *p;
    uint32_t sent = 0;

    if (platform_init() != 0) {
        printf("vlab-soc: platform_init failed\n");
        return 1;
    }
    if (platform_self_check() != 0) {
        printf("vlab-soc: platform self-check failed\n");
        return 2;
    }
    for (p = msg; *p; p++) {
        if (uart_write_byte((uint8_t)*p) != 0) {
            printf("vlab-soc: uart write failed\n");
            return 3;
        }
        soc_host_step(UART_LATENCY_STEPS); /* let the byte send */
        sent++;
    }
    /* Arm a one-shot timer and wait out its expiry. */
    timer_start(100, 0, 1);
    soc_host_step(100);
    if (!timer_fired()) {
        printf("vlab-soc: timer never fired\n");
        return 4;
    }
    timer_clear();
    printf("vlab-soc boot ok: hello sent, timer fired\n");
    printf("metrics: uart_bytes=%u timer_fired=1 mem_acc=%u stalls=%u\n",
           sent, hal_read_reg(VLAB_PERF_MEM_ACC),
           hal_read_reg(VLAB_PERF_STALLS));
    return 0;
}
