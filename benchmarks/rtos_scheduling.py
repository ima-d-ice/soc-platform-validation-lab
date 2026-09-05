#!/usr/bin/env python3
"""RTOS scheduling benchmark (Phase 6): priority/load/queue/periodic studies.

All time is virtual SoC model ticks shared by the SoC and the scheduler
(each scheduler tick steps the SoC once). Task work costs are MODEL
parameters in ticks. Statistics over measured latencies/periods are
DERIVED. Nothing uses wall-clock time.

Usage:
  python3 benchmarks/rtos_scheduling.py \
    --config configs/base.yaml \
    --reps 5 \
    --out results/rtos_scheduling.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rtos.kernel import RtosQueue, Scheduler
from rtos.tasks import (acquisition_task, diagnostic_task, processing_task,
                        telemetry_task)
from soc.soc import SoC, load_config

MEASURED = ["latencies", "periods", "deadline_misses", "max_queue_depth",
            "drops", "timeouts", "context_switches", "idle_ticks",
            "completions", "starvation_events", "total_ticks"]
DERIVED = ["mean", "p50", "p99", "max", "jitter", "miss_rate"]
MODELED = ["work_ticks", "period_ticks", "starvation_gap_ticks"]


def _pct(sorted_vals, pct):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1,
                   int(round((pct / 100.0) * len(sorted_vals) + 0.5)) - 1))
    return sorted_vals[k]


def _stats_list(vals):
    s = sorted(vals)
    n = len(s)
    return {"n": n, "mean": sum(s) / n if n else 0,
            "p50": _pct(s, 50), "p99": _pct(s, 99),
            "max": s[-1] if s else 0,
            "min": s[0] if s else 0}


def _jitter(vals):
    if len(vals) < 2:
        return 0
    return statistics.pstdev(vals)


def _starvation(sch, threshold):
    """Per-task max run-gap exceeding threshold (modeled definition)."""
    events = {}
    for t in sch.tasks:
        runs = t.run_ticks
        gap = max((b - a for a, b in zip(runs, runs[1:])), default=0)
        if gap > threshold:
            events[t.name] = gap
    return events


def run_pipeline(config, *, period=20, acq=1, proc=6, telem=2, qdepth=8,
                 deadline=60, proc_prio=4, telem_prio=2, max_items=40,
                 run_ticks=6000, starve_mult=5):
    """One fresh-SoC pipeline run. Returns measured + derived results."""
    soc = SoC(config)
    soc.boot()
    sch = Scheduler(soc)
    q1, q2 = RtosQueue("in", qdepth), RtosQueue("out", qdepth)
    sa, sp, st, sd = {}, {}, {}, {}
    sch.create_task("acq", 3, acquisition_task(period, acq, q1, deadline,
                                               sa, max_items=max_items))
    sch.create_task("proc", proc_prio, processing_task(q1, q2, proc, sp))
    sch.create_task("tele", telem_prio, telemetry_task(q2, telem, st))
    sch.create_task("diag", 1, diagnostic_task(50, sch, sd))
    sch.run(run_ticks)
    lat = st.get("latency", [])
    acq_periods = [b["actual"] - a["actual"]
                   for a, b in zip(sa.get("wake", []), sa.get("wake", [])[1:])]
    starve = _starvation(sch, starve_mult * period)
    timeouts = (q1.stats()["send_timeouts"] + q1.stats()["recv_timeouts"]
                + q2.stats()["send_timeouts"] + q2.stats()["recv_timeouts"])
    return {
        "params": {"period": period, "acq": acq, "proc": proc, "telem": telem,
                   "qdepth": qdepth, "deadline": deadline,
                   "proc_prio": proc_prio, "telem_prio": telem_prio,
                   "max_items": max_items, "run_ticks": run_ticks},
        "total_ticks": sch.now,  # measured
        "latencies": lat,  # measured
        "latency_stats": _stats_list(lat),  # derived
        "periods": acq_periods,  # measured actual acquisition periods
        "period_jitter": _jitter(acq_periods),  # derived
        "deadline_misses": st.get("misses", 0),  # measured
        "miss_rate": (st.get("misses", 0) / len(lat)) if lat else 0,  # derived
        "completions": len(lat),  # measured
        "produced": sa.get("produced", 0),  # measured
        "attempted": sa.get("attempted", 0),  # measured
        "max_queue_depth": max(q1.stats()["max_depth"],
                               q2.stats()["max_depth"]),  # measured
        "q1": q1.stats(), "q2": q2.stats(),  # measured
        "drops": q1.stats()["drops"] + q2.stats()["drops"]
        + sp.get("forward_drops", 0),  # measured
        "timeouts": timeouts,  # measured
        "context_switches": sch.context_switches,  # measured
        "idle_ticks": sch.idle_ticks,  # measured
        "starvation_events": starve,  # measured gaps vs modeled threshold
        "run_counts": {t.name: len(t.run_ticks) for t in sch.tasks},  # measured
        "provenance": {"measured": MEASURED, "derived": DERIVED,
                       "modeled": MODELED},
    }


def build_scenarios():
    # Workloads are sized so scheduling actually matters (overload where
    # the experiment needs contention); light cases stay as controls.
    scenarios = [
        ("priority/proc-high",
         dict(proc_prio=5, telem_prio=2, period=10, acq=1, proc=9, telem=5,
              qdepth=4, deadline=200, max_items=30, run_ticks=6000)),
        ("priority/telem-high",
         dict(proc_prio=2, telem_prio=5, period=10, acq=1, proc=9, telem=5,
              qdepth=4, deadline=200, max_items=30, run_ticks=6000)),
    ]
    for c in (1, 2, 4, 8, 12, 16):
        scenarios.append((f"load/proc-{c}",
                          dict(period=20, acq=1, proc=c, telem=2, qdepth=8,
                               deadline=9, max_items=30, run_ticks=6000)))
    for d in (1, 2, 4, 8, 16):
        scenarios.append((f"queue/depth-{d}",
                          dict(period=5, acq=0, proc=6, telem=2, qdepth=d,
                               deadline=100, max_items=40, run_ticks=6000)))
    for p in (10, 20, 40):
        scenarios.append((f"periodic/P-{p}",
                          dict(period=p, acq=1, proc=12, telem=2, qdepth=8,
                               deadline=3 * p, max_items=30, run_ticks=8000)))
    return scenarios


def main() -> int:
    ap = argparse.ArgumentParser(description="RTOS scheduling benchmark (measured).")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "results" / "rtos_scheduling.json"))
    ap.add_argument("--scenarios", default="all")
    args = ap.parse_args()
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")

    config = load_config(args.config)
    wanted = [s for s in args.scenarios.split(",") if s.strip()]
    scenarios = [(n, p) for n, p in build_scenarios()
                 if wanted == ["all"] or any(n == w or n.startswith(w + "/")
                                             or w == n.split("/")[0]
                                             for w in wanted)]
    if not scenarios:
        raise SystemExit("no scenarios selected")
    runs = []
    for rep in range(args.reps):
        for name, params in scenarios:
            row = run_pipeline(config, **params)
            row["scenario"] = name
            row["rep"] = rep
            runs.append(row)

    by_scen: dict[str, list] = {}
    for r in runs:
        by_scen.setdefault(r["scenario"], []).append(r)
    deterministic = all(
        len({(tuple(x["latencies"]), x["context_switches"],
              x["deadline_misses"]) for x in v}) == 1
        for v in by_scen.values()
    )
    summary = {}
    for name, v in by_scen.items():
        first = v[0]
        summary[name] = {
            "reps": len(v),
            "deterministic": len({(tuple(x["latencies"]),
                                   x["context_switches"]) for x in v}) == 1,
            "mean_latency": sum(x["latency_stats"]["mean"] for x in v) / len(v),
            "mean_p99": sum(x["latency_stats"]["p99"] for x in v) / len(v),
            "mean_jitter": sum(x["period_jitter"] for x in v) / len(v),
            "miss_rate": sum(x["miss_rate"] for x in v) / len(v),
            "mean_max_qdepth": sum(x["max_queue_depth"] for x in v) / len(v),
            "mean_ctx": sum(x["context_switches"] for x in v) / len(v),
            "completions": first["completions"],
            "starved": sorted({t for x in v for t in x["starvation_events"]}),
        }
    payload = {
        "params": {
            "config": pathlib.Path(args.config).name,
            "repetitions": args.reps,
            "deterministic_across_reps": deterministic,
            "note": "model ticks shared by SoC + scheduler; work costs modeled; "
                    "statistics derived from measured latencies/periods.",
        },
        "runs": runs,
        "summary": summary,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"config: {payload['params']['config']} scenarios={len(scenarios)} "
          f"reps={args.reps} deterministic={deterministic}")
    print(f"{'scenario':>20} {'lat_mean':>8} {'lat_p99':>7} {'jitter':>7} "
          f"{'miss%':>6} {'qmax':>4} {'ctx':>5} {'done':>4} {'starved'}")
    for name in summary:
        s = summary[name]
        print(f"{name:>20} {s['mean_latency']:>8.1f} {s['mean_p99']:>7.0f} "
              f"{s['mean_jitter']:>7.2f} {100*s['miss_rate']:>5.1f}% "
              f"{s['mean_max_qdepth']:>4.0f} {s['mean_ctx']:>5.0f} "
              f"{s['completions']:>4} {s['starved']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
