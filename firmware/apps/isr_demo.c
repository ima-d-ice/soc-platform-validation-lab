/* Event-driven firmware demo: DMA lifecycle under a system state machine.
 *
 * System states: IDLE -> STARTING -> ACTIVE -> COMPLETE -> IDLE, with
 * ACTIVE -> ERROR -> RECOVERY -> IDLE on timeout or engine error.
 *
 * HOST HONESTY: the host has no ticking engine, so STARTed transfers do
 * not complete by themselves. The demo drives completion two ways, both
 * stated: (1) the completion leg uses vlab_test_dma_complete() as an
 * explicit host stand-in for "the engine finished and raised the IRQ";
 * the ISR dispatch, flags, and two-step clear are the real code paths.
 * (2) the error leg forces a DMA error the same way. Timeout waits use a
 * bounded poll loop (the same pattern as uart_write_byte); on silicon the
 * bound would be a timer. State transitions, init sequencing, and
 * recovery are genuine firmware logic either way.
 */
#include <stdio.h>

#include "driver_api.h"
#include "hal.h"
#include "isr.h"
#include "soc_regs.h"

#define DEMO_SRC 0x10000000U
#define DEMO_DST 0x10001000U
#define DEMO_LEN 256U
#define POLL_BOUND 100000

typedef enum {
    SYS_IDLE = 0,
    SYS_STARTING,
    SYS_ACTIVE,
    SYS_COMPLETE,
    SYS_ERROR,
    SYS_RECOVERY
} sys_state_t;

static volatile sys_state_t s_sys = SYS_IDLE;

static const char *state_name(sys_state_t s) {
    switch (s) {
        case SYS_IDLE: return "IDLE";
        case SYS_STARTING: return "STARTING";
        case SYS_ACTIVE: return "ACTIVE";
        case SYS_COMPLETE: return "COMPLETE";
        case SYS_ERROR: return "ERROR";
        case SYS_RECOVERY: return "RECOVERY";
        default: return "?";
    }
}

static void note(const char *what) {
    printf("demo: %-10s sys=%s dma_state=%d\n", what, state_name(s_sys),
           (int)dma_state());
}

/* Ordered bring-up: UART -> timer -> INTC+ISRs -> DMA. Any failure
 * propagates its code; later stages never run on an earlier failure. */
static int sys_init(void) {
    if (boot_init() != 0) return 10;
    if (timer_start(1000, 0, 1) != 0) return 11;
    intc_enable((1U << VLAB_IRQ_DMA) | (1U << VLAB_IRQ_TIMER));
    isr_register(VLAB_IRQ_DMA, dma_isr);
    if (dma_state() != DMA_S_IDLE) return 12;
    return 0;
}

/* One transfer leg. complete_it nonzero: engine stand-in completes it;
 * zero: engine error is forced instead. Returns 0 on COMPLETE. */
static int run_leg(int complete_it) {
    s_sys = SYS_STARTING;
    note("submit");
    if (dma_submit(DEMO_SRC, DEMO_DST, DEMO_LEN, 1) != VLAB_DMA_OK) {
        s_sys = SYS_ERROR;
        note("submit-fail");
        return -1;
    }
    s_sys = SYS_ACTIVE;
    /* Engine stand-in (host only; silicon: IRQ arrives on its own). */
    if (complete_it)
        vlab_test_dma_complete();
    else
        vlab_test_dma_error(1U);
    /* Bounded completion wait with ISR dispatch (main-loop pattern). */
    int i;
    for (i = 0; i < POLL_BOUND; i++) {
        isr_dispatch();
        if (dma_is_complete() || dma_state() == DMA_S_ERROR) break;
    }
    if (i == POLL_BOUND) {
        s_sys = SYS_ERROR; /* timeout path */
        note("timeout");
        return -2;
    }
    if (dma_state() == DMA_S_COMPLETE) {
        s_sys = SYS_COMPLETE;
        note("complete");
        dma_recover();
        s_sys = SYS_IDLE;
        return 0;
    }
    s_sys = SYS_ERROR;
    note("engine-error");
    return -3;
}

static int run_recovery_leg(void) {
    /* From ERROR back to a working transfer: recover, then run clean. */
    s_sys = SYS_RECOVERY;
    note("recover");
    dma_recover();
    if (dma_state() != DMA_S_IDLE) return -1;
    s_sys = SYS_IDLE;
    return run_leg(1);
}

int demo_main(void) {
    int rc = sys_init();
    if (rc != 0) {
        printf("demo: init failed rc=%d\n", rc);
        return 1;
    }
    note("init-ok");
    if (run_leg(1) != 0) {
        printf("demo: completion leg failed\n");
        return 2;
    }
    if (run_leg(0) == 0) {
        printf("demo: error leg unexpectedly succeeded\n");
        return 3;
    }
    if (dma_state() != DMA_S_ERROR ||
        dma_latched_error() != 1U) {
        printf("demo: error state not latched\n");
        return 4;
    }
    if (run_recovery_leg() != 0) {
        printf("demo: recovery leg failed\n");
        return 5;
    }
    if (dma_state() != DMA_S_IDLE || isr_dispatched_count() < 3U) {
        printf("demo: final state wrong\n");
        return 6;
    }
    printf("DEMO OK: complete+error+recovery legs passed\n");
    return 0;
}

int main(void) { return demo_main(); }
