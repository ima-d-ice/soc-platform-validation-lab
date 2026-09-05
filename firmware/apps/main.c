/* Minimal application: boots, sends UART hello, arms a timer. */
#include <stdio.h>

#include "driver_api.h"

int boot_self_check(void);

int main(void) {
    if (boot_init() != 0) {
        printf("vlab-soc: boot_init failed\n");
        return 1;
    }
    if (boot_self_check() != 0) {
        printf("vlab-soc: boot self-check failed\n");
        return 2;
    }
    const char *msg = "hello vlab-soc";
    for (const char *p = msg; *p; p++) {
        if (uart_write_byte((uint8_t)*p) != 0) {
            printf("vlab-soc: uart write failed\n");
            return 3;
        }
    }
    /* Arm a one-shot timer (host shim stores config; expiry in the model). */
    timer_start(100, 0, 1);
    printf("vlab-soc boot ok: hello sent, timer armed\n");
    return 0;
}
