# RTOS note

Real-time scheduling for this platform is modeled in `rtos/` (Python,
deterministic, on the shared SoC model clock) — see `docs/rtos.md` for the
exact semantics mapping. A wall-clock FreeRTOS port was deliberately not
vendored: it would break run-to-run determinism, which every benchmark in
this repo guarantees. No C RTOS code lives here by design.
