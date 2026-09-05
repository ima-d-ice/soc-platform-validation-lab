#!/usr/bin/env python3
"""Linux-facing platform benchmark (Phase 7): buffer/completion/size studies.

Userspace driver model over the virtual SoC (see docs/linux-platform.md).
All ticks/counters are read from the model (measured); statistics are
derived; work sizes, consumer pacing, and budgets are modeled parameters.
No wall-clock use. Explicitly not a kernel driver measurement.

Usage:
  python3 benchmarks/linux_platform.py \
    --config configs/base.yaml \
    --sizes 64,256,1024,4096,16384 \
    --reps 5 \
    --out results/linux_platform.json
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from linux.app import StreamApp
from linux.driver import StreamDriver
from soc.soc import SoC, load_config

DEFAULT_SIZES = (64, 256, 1024, 4096, 16384)
DEFAULT_BUFFERS = (1, 2, 4, 8)
MODES = ("polling", "irq")

MEASURED = ["submit_ticks", "completion_ticks", "e2e_ticks", "throughput",
            "queue_depth", "drops", "mem_accesses", "dma_bytes",
            "notifications", "mismatches"]
DERIVED = ["mean", "p50", "p99", "max"]
MODELED = ["transfer_bytes", "buffer_count", "consumer_period", "frame_count"]


def _expected_xfer(nbytes, burst, lat):
    words = math.ceil(nbytes / 4)
    bursts = math.ceil(words / burst)
    return max(1, words * lat + (bursts - 1))


def _frames_for(size):
    return max(4, min(32, 65536 // size))


def _stats(vals):
    s = sorted(vals)
    n = len(s)
    if not n:
        return {"n": 0, "mean": 0, "p50": 0, "p99": 0, "max": 0}
    pct = lambda p: s[max(0, min(n - 1, int(round(p / 100 * n + 0.5)) - 1))]
    return {"n": n, "mean": sum(s) / n, "p50": pct(50), "p99": pct(99),
            "max": s[-1]}


def run_cell(config, size, depth, mode):
    """Fresh SoC + driver per cell; paced streaming run."""
    soc = SoC(config)
    soc.boot()
    t0_mem = soc.perf.mem_acc
    t0_dma = soc.perf.dma_bytes
    t0_irq = soc.perf.irq_count
    t0 = soc.ticks
    drv = StreamDriver(soc, ring_depth=depth)
    drv.init(irq_mode=(mode == "irq"))
    # Buffers are capped by the 32KB arena; the ring depth still applies and
    # buffer-busy refusals are measured as drops (documented in the driver).
    nbufs = max(1, min(depth, 32768 // size))
    bufs = [drv.alloc(size) for _ in range(nbufs)]
    xfer = _expected_xfer(size, config.get("dma_burst", 4),
                          config.get("dma_latency_per_word_ticks", 1))
    app = StreamApp(drv, consumer_period=max(1, xfer))
    nframes = _frames_for(size)
    out = app.run([(bufs[i % len(bufs)], size, 0xD0000000 + i)
                   for i in range(nframes)])
    total = soc.ticks - t0
    assert out["mismatches"] == 0
    assert out["completed"] == nframes
    lat = _stats(out["latencies"])
    moved = nframes * size
    return {
        "transfer_size": size,  # modeled
        "buffers": depth,  # modeled
        "completion": mode,
        "frames": nframes,  # modeled
        "consumer_period": max(1, xfer),  # modeled
        "submit_ticks": 0,  # measured: submission is combinational MMIO
        "completion_ticks": lat["mean"],  # measured mean e2e per frame
        "e2e_stats": lat,  # measured latencies + derived stats
        "total_ticks": total,  # measured
        "throughput": moved / total if total else 0,  # derived B/tick
        "latencies": out["latencies"],  # measured per-frame e2e ticks
        "queue_depth": drv.max_outstanding,  # measured high-water mark
        "drops": out["dropped"],  # measured refused submits (retried)
        "mem_accesses": soc.perf.mem_acc - t0_mem,  # measured
        "dma_bytes": soc.perf.dma_bytes - t0_dma,  # measured
        "notifications": out["notifications"],  # measured
        "poll_reads": out["poll_reads"],  # measured
        "mismatches": 0,  # measured
        "provenance": {"measured": MEASURED, "derived": DERIVED,
                       "modeled": MODELED},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Linux platform benchmark (measured).")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    ap.add_argument("--buffers", default=",".join(map(str, DEFAULT_BUFFERS)))
    ap.add_argument("--completion", default="both",
                    choices=("polling", "irq", "both"))
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "results" / "linux_platform.json"))
    args = ap.parse_args()
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")

    config = load_config(args.config)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    depths = [int(b) for b in args.buffers.split(",") if b.strip()]
    modes = list(MODES) if args.completion == "both" else [args.completion]
    for s in sizes:
        if s % 4 != 0 or s <= 0 or s > 16384:
            raise SystemExit(f"size {s}: must be %4==0 within 16KB SRAM cap")

    runs = []
    for rep in range(args.reps):
        for size in sizes:
            for depth in depths:
                for mode in modes:
                    row = run_cell(config, size, depth, mode)
                    row["rep"] = rep
                    runs.append(row)

    by_key: dict[tuple, list] = {}
    for r in runs:
        by_key.setdefault((r["transfer_size"], r["buffers"],
                           r["completion"]), []).append(r)
    deterministic = all(
        len({(x["total_ticks"], x["drops"], x["notifications"],
              tuple(x["latencies"]), x["mem_accesses"]) for x in v}) == 1
        for v in by_key.values()
    )
    summary = {}
    for key, v in by_key.items():
        size, depth, mode = key
        summary[f"{size}B/b{depth}/{mode}"] = {
            "reps": len(v),
            "mean_e2e": sum(x["completion_ticks"] for x in v) / len(v),
            "mean_p99": sum(x["e2e_stats"]["p99"] for x in v) / len(v),
            "mean_throughput": sum(x["throughput"] for x in v) / len(v),
            "mean_qdepth": sum(x["queue_depth"] for x in v) / len(v),
            "mean_drops": sum(x["drops"] for x in v) / len(v),
            "mean_mem": sum(x["mem_accesses"] for x in v) / len(v),
            "notifications": v[0]["notifications"],
        }
    payload = {
        "params": {
            "config": pathlib.Path(args.config).name,
            "config_values": {
                "cpu_frequency_mhz": config.get("cpu_frequency_mhz"),
                "dma_burst": config.get("dma_burst"),
                "dma_latency_per_word_ticks": config.get(
                    "dma_latency_per_word_ticks")},
            "transfer_sizes": sizes, "buffer_counts": depths,
            "completion_modes": modes, "repetitions": args.reps,
            "deterministic_across_reps": deterministic,
            "note": "userspace driver model; ticks/counters measured in the "
                    "virtual SoC model; statistics derived; sizes/pacing modeled.",
        },
        "runs": runs,
        "summary": summary,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"config: {payload['params']['config']} sizes={sizes} bufs={depths} "
          f"modes={modes} reps={args.reps} deterministic={deterministic}")
    print(f"{'cell':>22} {'e2e':>7} {'p99':>7} {'B/t':>6} "
          f"{'qmax':>4} {'drops':>6} {'notif':>5}")
    for k in summary:
        s = summary[k]
        print(f"{k:>22} {s['mean_e2e']:>7.1f} {s['mean_p99']:>7.0f} "
              f"{s['mean_throughput']:>6.3f} {s['mean_qdepth']:>4.0f} "
              f"{s['mean_drops']:>6.0f} {s['notifications']:>5}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
