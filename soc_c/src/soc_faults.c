#include "soc_faults.h"

#include <string.h>

#include "soc.h"

void soc_recovery_init(soc_recovery_tracker_t *t) {
    memset(t, 0, sizeof(*t));
    t->current = SOC_RS_NORMAL;
}

int soc_recovery_on_fault(soc_recovery_tracker_t *t, int tick,
                          const char *fault_type) {
    if (t->current != SOC_RS_NORMAL) return -1;
    strncpy(t->fault_type, fault_type, SOC_FAULT_NAME_MAX - 1);
    t->fault_time = tick;
    t->has_fault = 1;
    return 0;
}

int soc_recovery_on_detected(soc_recovery_tracker_t *t, int tick) {
    if (t->current != SOC_RS_NORMAL) return -1;
    t->current = SOC_RS_FAULT_DETECTED;
    t->detection_time = tick;
    t->has_detection = 1;
    return 0;
}

int soc_recovery_on_recovery_start(soc_recovery_tracker_t *t) {
    if (t->current != SOC_RS_FAULT_DETECTED) return -1;
    t->current = SOC_RS_RECOVERY;
    return 0;
}

int soc_recovery_on_recovered(soc_recovery_tracker_t *t, int tick) {
    if (t->current != SOC_RS_RECOVERY) return -1;
    t->current = SOC_RS_RECOVERED;
    t->recovery_time = tick;
    t->has_recovery = 1;
    return 0;
}

int soc_recovery_on_unrecoverable(soc_recovery_tracker_t *t, int tick) {
    t->current = SOC_RS_UNRECOVERABLE;
    t->recovery_time = tick;
    t->has_recovery = 1;
    return 0;
}

void soc_fault_injector_init(soc_fault_injector_t *fi, struct soc_t *soc) {
    fi->soc = soc;
    fi->n_active = 0;
    memset(fi->active, 0, sizeof(fi->active));
}

static void soc_apply_latch(struct soc_t *soc, const char *name, int on) {
    soc_t *s = soc;
    if (strcmp(name, "dma-timeout") == 0) {
        s->dma.fault_stuck_busy = on ? 1 : 0;
    } else if (strcmp(name, "uart-stuck-busy") == 0) {
        s->uart.fault_stuck_busy = on ? 1 : 0;
    }
}

int soc_fault_inject(soc_fault_injector_t *fi, const char *name) {
    int i;
    for (i = 0; i < fi->n_active; i++) {
        if (strcmp(fi->active[i], name) == 0) return 0;
    }
    if (fi->n_active < 4) {
        strncpy(fi->active[fi->n_active], name, SOC_FAULT_NAME_MAX - 1);
        fi->n_active++;
    }
    soc_apply_latch(fi->soc, name, 1);
    return 0;
}

void soc_fault_clear(soc_fault_injector_t *fi, const char *name) {
    int i, j;
    for (i = 0; i < fi->n_active; i++) {
        if (strcmp(fi->active[i], name) == 0) {
            for (j = i; j + 1 < fi->n_active; j++)
                strcpy(fi->active[j], fi->active[j + 1]);
            fi->n_active--;
            break;
        }
    }
    soc_apply_latch(fi->soc, name, 0);
}

int soc_fault_is_active(soc_fault_injector_t *fi, const char *name) {
    int i;
    for (i = 0; i < fi->n_active; i++) {
        if (strcmp(fi->active[i], name) == 0) return 1;
    }
    return 0;
}
