#!/usr/bin/env python3
"""Boot-time benchmark: real measurement from the virtual SoC model.

Measures ticks from Reset to main entry across N runs on a given config.
Writes JSON to results/boot_time.json. Never synthesised.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soc.soc import SoC, load_config


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure vlab-soc boot time.")
    ap.add_argument("--config", default=str(ROOT / "configs" / "base.yaml"))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "results" / "boot_time.json"))
    args = ap.parse_args()

    config = load_config(args.config)
    runs = []
    for _ in range(args.runs):
        soc = SoC(config)
        info = soc.boot()
        runs.append(
            {
                "boot_ticks": info["boot_ticks"],
                "boot_ns": info["boot_ns"],
                "cycles": soc.perf.cycles,
                "mem_acc": soc.perf.mem_acc,
            }
        )

    ticks = [r["boot_ticks"] for r in runs]
    result = {
        "config": pathlib.Path(args.config).name,
        "cpu_frequency_mhz": config.get("cpu_frequency_mhz"),
        "runs": runs,
        "summary": {
            "n": len(runs),
            "min_ticks": min(ticks),
            "max_ticks": max(ticks),
            "mean_ticks": sum(ticks) / len(ticks),
            "deterministic": len(set(ticks)) == 1,
        },
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"config: {result['config']}  runs: {len(runs)}")
    for r in runs:
        print(f"  boot_ticks={r['boot_ticks']} boot_ns={r['boot_ns']} "
              f"cycles={r['cycles']} mem_acc={r['mem_acc']}")
    s = result["summary"]
    print(f"summary: min={s['min_ticks']} max={s['max_ticks']} "
          f"mean={s['mean_ticks']:.2f} deterministic={s['deterministic']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
