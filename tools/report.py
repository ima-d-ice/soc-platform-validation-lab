#!/usr/bin/env python3
"""Minimal results reporter: pretty-print results/*.json as markdown table."""
from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    files = sorted((root / "results").glob("*.json"))
    if not files:
        print("report: no results/*.json found")
        return 1
    for f in files:
        data = json.loads(f.read_text())
        print(f"## {f.name}")
        print(f"config: {data.get('config')}")
        for r in data.get("runs", []):
            print(f"- {r}")
        print(f"summary: {data.get('summary')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
