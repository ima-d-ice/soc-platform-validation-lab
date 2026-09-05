#!/usr/bin/env python3
"""Deferred: CPU memcpy vs DMA transfer comparison.

Not implemented in MVP (§1–§5). Will measure transfer latency, CPU
involvement, throughput and interrupt count for identical workloads once
burst/chained DMA lands. This stub exists to reserve the CLI surface.
"""
from __future__ import annotations

if __name__ == "__main__":
    print("cpu_vs_dma: deferred (needs burst/chained DMA + perf analysis)")
    raise SystemExit(2)
