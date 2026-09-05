"""Driver abstraction: init/configure/submit/complete over DMA-style buffers.

Single DMA channel (model fact): at most one transfer is active on the
engine at a time. The ring therefore queues *descriptors* (seed + buffer +
size); payload is CPU-filled into the single staging area at START time,
so queued frames never overwrite each other. A paced consumer draining
slower than the producer fills the ring -> drops (counted); a deep ring
absorbs bursts but lengthens end-to-end waits. All of this is measured,
not assumed.

Buffer handles are opaque integers; SRAM addresses never leak to the app.
Completion via STATUS polling or IRQ notification. Timeouts and DMA errors
raise StreamError; illegal accesses propagate BusError unchanged.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from soc.bus import BusError

from .mmio import IRQ_DMA, IRQ_NONE, ST_BUSY, ST_DONE, ST_ERROR, DeviceRegs

STAGING_BASE = 0x10000000  # CPU-filled frame source (documented, driver-only)
STAGING_SIZE = 0x4000  # 16KB max single frame
ARENA_BASE = 0x10004000  # DMA destination arena (driver-only)
ARENA_SIZE = 0x8000  # 32KB


class StreamError(Exception):
    """Driver-level failure: timeout, DMA error, exhaustion, bad argument."""


@dataclass
class Frame:
    handle: int
    nbytes: int
    seed: int
    t_enqueued: int = 0
    t_start: int = -1
    t_complete: int = -1
    mode: str = ""


@dataclass
class Ticket:
    frame: Frame
    done: bool = False


class StreamDriver:
    def __init__(self, soc, *, ring_depth=4):
        assert ring_depth >= 1
        self.soc = soc
        self.regs = DeviceRegs(soc)
        self.ring_depth = ring_depth
        self._arena_next = ARENA_BASE
        self._bufs: dict[int, int] = {}  # handle -> SRAM address
        self._next_handle = 1
        self._queue: deque[Frame] = deque()  # staged descriptors
        self._active: Frame | None = None  # on the engine now
        self._inflight_frames: list[Frame] = []  # queued + active
        self.max_outstanding = 0  # measured high-water mark
        self.notifications = 0  # IRQ-path completions observed
        self.poll_reads = 0  # STATUS reads performed while polling
        self.timeouts = 0
        self.drops = 0  # try_submit refusals (ring full)
        self.completed = 0
        self._opened = False
        self.irq_mode = False

    # -- lifecycle: init / configure / close --
    def init(self, *, irq_mode: bool) -> None:
        """Device initialization: idle engine, clear IRQ state, IRQ config."""
        self.soc.dma.reset()
        self.regs.dma_clear()
        self.regs.irq_enable_dma(irq_mode)
        if self.regs.irq_pending_dma():
            if self.regs.irq_ack() != IRQ_NONE:
                self.regs.irq_clear(IRQ_DMA)
        self.irq_mode = irq_mode
        self._opened = True

    def close(self) -> None:
        self.regs.irq_enable_dma(False)
        self.soc.dma.reset()
        self._queue.clear()
        self._active = None
        self._inflight_frames.clear()
        self._opened = False

    def abort(self) -> None:
        """Abort current activity after a timeout/fault; engine to idle."""
        self.soc.dma.reset()
        self.regs.dma_clear()
        if self.regs.irq_pending_dma():
            if self.regs.irq_ack() != IRQ_NONE:
                self.regs.irq_clear(IRQ_DMA)
        self._queue.clear()
        self._active = None
        self._inflight_frames.clear()

    def _require_open(self) -> None:
        if not self._opened:
            raise StreamError("device not initialized")

    # -- buffers: alloc (opaque handles) --
    def alloc(self, nbytes: int) -> int:
        self._require_open()
        if nbytes <= 0 or nbytes % 4 != 0:
            raise StreamError(f"bad buffer size {nbytes}")
        addr = (self._arena_next + 3) & ~0x3
        if addr + nbytes > ARENA_BASE + ARENA_SIZE:
            raise StreamError("buffer arena exhausted")
        if nbytes > STAGING_SIZE:
            raise StreamError("transfer exceeds staging area")
        self._arena_next = addr + nbytes
        handle = self._next_handle
        self._next_handle += 1
        self._bufs[handle] = addr
        return handle

    # -- submit path --
    def _fill_staging(self, frame: Frame) -> None:
        for i in range(frame.nbytes // 4):
            self.soc.sram_write_word(STAGING_BASE + i * 4,
                                     frame.seed ^ i)

    def _engine_idle(self) -> bool:
        return not (self.regs.dma_status() & (ST_BUSY | ST_DONE | ST_ERROR))

    def pump(self) -> None:
        """START the oldest queued frame if the engine is idle."""
        self._require_open()
        if self._active is not None:
            return  # completion handled by wait()/collect_ready()
        if not self._queue:
            return
        st = self.regs.dma_status()
        if st & ST_BUSY:
            return
        if st & (ST_DONE | ST_ERROR):
            raise StreamError("stale completion with no active frame")
        frame = self._queue.popleft()
        self._fill_staging(frame)
        dst = self._bufs[frame.handle]
        self.regs.dma_program(STAGING_BASE, dst, frame.nbytes,
                              self.irq_mode)
        frame.t_start = self.soc.ticks
        frame.mode = "irq" if self.irq_mode else "polling"
        self._active = frame

    def _handle_busy(self, handle: int) -> bool:
        return any(f.handle == handle for f in self._inflight_frames)

    def submit(self, handle: int, nbytes: int, seed: int,
               *, timeout: int | None = None) -> Ticket:
        """Enqueue a frame, blocking (with tick timeout) if ring is full."""
        self._require_open()
        if handle not in self._bufs:
            raise StreamError(f"unknown buffer {handle}")
        waited = 0
        while (len(self._inflight_frames) >= self.ring_depth
               or self._handle_busy(handle)):
            if timeout is not None and waited >= timeout:
                self.timeouts += 1
                raise StreamError("submit timeout: ring full")
            self.soc.step(1)
            waited += 1
        frame = Frame(handle, nbytes, seed, t_enqueued=self.soc.ticks)
        self._queue.append(frame)
        self._inflight_frames.append(frame)
        self.max_outstanding = max(self.max_outstanding,
                                   len(self._inflight_frames))
        self.pump()
        return Ticket(frame)

    def try_submit(self, handle: int, nbytes: int, seed: int):
        """Non-blocking submit: None + drop count if ring is full."""
        self._require_open()
        if handle not in self._bufs:
            raise StreamError(f"unknown buffer {handle}")
        if (len(self._inflight_frames) >= self.ring_depth
                or self._handle_busy(handle)):
            self.drops += 1
            return None
        frame = Frame(handle, nbytes, seed, t_enqueued=self.soc.ticks)
        self._queue.append(frame)
        self._inflight_frames.append(frame)
        self.max_outstanding = max(self.max_outstanding,
                                   len(self._inflight_frames))
        self.pump()
        return Ticket(frame)

    # -- completion path --
    def _collect_active(self) -> Frame:
        frame = self._active
        assert frame is not None
        if self.irq_mode:
            assert self.regs.irq_pending_dma(), "IRQ completion expected"
            acked = self.regs.irq_ack()
            assert acked == IRQ_DMA, f"unexpected ACK {acked}"
            self.regs.irq_clear(IRQ_DMA)
            self.notifications += 1
        else:
            assert not self.regs.irq_pending_dma(), "polling must not IRQ"
        self.regs.dma_clear()
        frame.t_complete = self.soc.ticks
        self._active = None
        self._inflight_frames.remove(frame)
        self.completed += 1
        return frame

    def wait(self, ticket: Ticket, *, timeout: int | None = None) -> int:
        """Wait for one frame; returns completion tick. Raises StreamError."""
        self._require_open()
        elapsed = 0
        while True:
            self.pump()
            st = self.regs.dma_status()
            if st & ST_DONE:
                break
            if st & ST_ERROR:
                code = self.regs.dma_error()
                raise StreamError(f"DMA error code {code}")
            if timeout is not None and elapsed >= timeout:
                self.timeouts += 1
                raise StreamError("completion timeout")
            if not self.irq_mode:
                self.poll_reads += 1
            self.soc.step(1)
            elapsed += 1
        assert self._active is ticket.frame, "completion ordering violated"
        self._collect_active()
        ticket.done = True
        return ticket.frame.t_complete

    def collect_ready(self) -> list[Ticket]:
        """Non-blocking reap of a finished active frame (paced consumer)."""
        self._require_open()
        self.pump()
        st = self.regs.dma_status()
        if self._active is None or not (st & (ST_DONE | ST_ERROR)):
            return []
        if st & ST_ERROR:
            code = self.regs.dma_error()
            raise StreamError(f"DMA error code {code}")
        frame = self._collect_active()
        return [Ticket(frame, done=True)]

    def outstanding(self) -> int:
        return len(self._inflight_frames)

    # -- consumer: verify data integrity --
    def verify(self, ticket: Ticket) -> bool:
        frame = ticket.frame
        addr = self._bufs[frame.handle]
        for i in range(frame.nbytes // 4):
            if self.soc.sram_read_word(addr + i * 4) != (frame.seed ^ i):
                return False
        return True

    def stats(self) -> dict:
        return {"notifications": self.notifications,
                "poll_reads": self.poll_reads, "timeouts": self.timeouts,
                "drops": self.drops, "completed": self.completed,
                "inflight": len(self._inflight_frames)}
