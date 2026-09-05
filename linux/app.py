"""Application API: thin streaming consumer over the driver.

Knows nothing about SRAM addresses, registers, or the DMA engine: frames
are submitted by (handle, size, seed) and completions return latencies.
Data integrity is checked through driver.verify().
"""
from __future__ import annotations

from .driver import StreamDriver


class StreamApp:
    """Paced producer/consumer: back-to-back try_submit, drain every period."""

    def __init__(self, driver: StreamDriver, *, consumer_period: int):
        assert consumer_period >= 1
        self.driver = driver
        self.consumer_period = consumer_period
        self.latencies: list[int] = []
        self.mismatches = 0

    def _reap(self) -> None:
        while True:
            done = self.driver.collect_ready()
            if not done:
                return
            for t in done:
                self.latencies.append(
                    t.frame.t_complete - t.frame.t_enqueued)
                if not self.driver.verify(t):
                    self.mismatches += 1

    def run(self, frames: list[tuple[int, int, int]]) -> dict:
        """frames: [(handle, nbytes, seed)]. Returns measured summary."""
        idx = 0
        submitted = 0
        ticks_left = 0
        while idx < len(frames) or self.driver.outstanding():
            # Producer: back-to-back non-blocking submits.
            while idx < len(frames):
                if self.driver.try_submit(*frames[idx]) is None:
                    break  # ring full -> counted drop; retry next tick
                idx += 1
                submitted += 1
            # Consumer: paced drain.
            if ticks_left <= 0:
                self._reap()
                ticks_left = self.consumer_period
            self.driver.soc.step(1)
            ticks_left -= 1
            self.driver.pump()
        self._reap()  # final drain
        stats = self.driver.stats()
        return {"submitted": submitted, "dropped": stats["drops"],
                "completed": stats["completed"],
                "mismatches": self.mismatches,
                "latencies": self.latencies,
                "notifications": stats["notifications"],
                "poll_reads": stats["poll_reads"]}


__all__ = ["StreamApp"]
