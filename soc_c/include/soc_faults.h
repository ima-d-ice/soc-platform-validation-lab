/* Deterministic fault injection + recovery tracking.
 * Mirrors soc/faults.py (additive: latching faults default off).
 */
#ifndef SOC_C_FAULTS_H
#define SOC_C_FAULTS_H

#include <stdint.h>

struct soc_t;

#define SOC_FAULT_NAME_MAX 32

typedef struct {
    char name[SOC_FAULT_NAME_MAX];
    int at_tick; /* -1 = immediate/event only */
} soc_fault_t;

typedef enum {
    SOC_RS_NORMAL = 0,
    SOC_RS_FAULT_DETECTED,
    SOC_RS_RECOVERY,
    SOC_RS_RECOVERED,
    SOC_RS_UNRECOVERABLE
} soc_recovery_state_t;

typedef struct {
    soc_recovery_state_t current;
    char fault_type[SOC_FAULT_NAME_MAX];
    int has_fault;
    int fault_time;
    int detection_time;
    int recovery_time;
    int has_detection;
    int has_recovery;
} soc_recovery_tracker_t;

void soc_recovery_init(soc_recovery_tracker_t *t);
int soc_recovery_on_fault(soc_recovery_tracker_t *t, int tick,
                          const char *fault_type);
int soc_recovery_on_detected(soc_recovery_tracker_t *t, int tick);
int soc_recovery_on_recovery_start(soc_recovery_tracker_t *t);
int soc_recovery_on_recovered(soc_recovery_tracker_t *t, int tick);
int soc_recovery_on_unrecoverable(soc_recovery_tracker_t *t, int tick);

typedef struct {
    struct soc_t *soc;
    /* active latch names (small fixed set, no heap) */
    char active[4][SOC_FAULT_NAME_MAX];
    int n_active;
} soc_fault_injector_t;

void soc_fault_injector_init(soc_fault_injector_t *fi, struct soc_t *soc);
int soc_fault_inject(soc_fault_injector_t *fi, const char *name);
void soc_fault_clear(soc_fault_injector_t *fi, const char *name);
int soc_fault_is_active(soc_fault_injector_t *fi, const char *name);

#endif /* SOC_C_FAULTS_H */
