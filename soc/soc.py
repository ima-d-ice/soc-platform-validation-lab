"""Top-level virtual SoC: bus decode + tick stepping + boot."""
from __future__ import annotations

import pathlib

import yaml

from .bus import BusError
from .cpu import Cpu
from .dma import Dma
from .interrupts import Intc
from .memory import SimpleMemory
from .perf import Perf
from .timer import Timer
from .uart import Uart

ROM_BASE = 0x00000000
SRAM_BASE = 0x10000000
UART_BASE = 0x20000000
TIMER_BASE = 0x20001000
DMA_BASE = 0x20002000
INTC_BASE = 0x20003000
PERF_BASE = 0x20004000
REGION_SIZE = 0x1000

BOOT_TICKS = 5  # Reset -> ROM -> stack -> .data/.bss -> main


def load_config(path: str | pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SoC:
    """Deterministic tick-stepped SoC model (MVP)."""

    def __init__(self, config: dict):
        self.config = config
        rom_size = int(config.get("rom_size_bytes", 16384))
        sram_size = int(config.get("sram_size_bytes", 65536))
        self.rom = SimpleMemory(ROM_BASE, rom_size, readonly=True, name="ROM")
        self.sram = SimpleMemory(SRAM_BASE, sram_size, readonly=False, name="SRAM")

        self.perf = Perf()
        self.intc = Intc(perf=self.perf)
        self.uart = Uart(
            latency_ticks=int(config.get("uart_latency_ticks", 5)),
            perf=self.perf,
            intc=self.intc,
        )
        self.timer = Timer(intc=self.intc)
        self.dma = Dma(
            sram_base=SRAM_BASE,
            sram_size=sram_size,
            latency_per_word=int(config.get("dma_latency_per_word_ticks", 1)),
            burst=int(config.get("dma_burst", 4)),
            intc=self.intc,
            perf=self.perf,
            mem_reader=self._sram_read_bytes,
            mem_writer=self._sram_write_bytes,
        )
        self.cpu = Cpu(rom_base=ROM_BASE, sram_top=SRAM_BASE + sram_size)
        self.ticks = 0
        self.trace: list[tuple[int, str]] = []

    # -- SRAM byte bridge for DMA --
    def _sram_read_bytes(self, addr: int, length: int) -> bytes:
        return self.sram.read_bytes(addr, length)

    def _sram_write_bytes(self, addr: int, payload: bytes) -> None:
        self.sram.write_bytes(addr, payload)

    # -- peripheral reset --
    def reset_peripherals(self) -> None:
        self.uart.reset()
        self.timer.reset()
        self.dma.reset()
        self.intc.reset()

    # -- MMIO --
    def _route(self, addr: int):
        if self.rom.contains(addr):
            return "rom"
        if self.sram.contains(addr):
            return "sram"
        for base, name in (
            (UART_BASE, "uart"),
            (TIMER_BASE, "timer"),
            (DMA_BASE, "dma"),
            (INTC_BASE, "intc"),
            (PERF_BASE, "perf"),
        ):
            if base <= addr < base + REGION_SIZE:
                return name
        return None

    def read(self, addr: int) -> int:
        if addr % 4 != 0:
            self.perf.count_stall()
            raise BusError(f"bus: unaligned read 0x{addr:08X}")
        self.perf.count_mem()
        kind = self._route(addr)
        try:
            if kind == "rom":
                return self.rom.read_word(addr)
            if kind == "sram":
                return self.sram.read_word(addr)
            if kind == "uart":
                return self.uart.read(addr - UART_BASE)
            if kind == "timer":
                return self.timer.read(addr - TIMER_BASE)
            if kind == "dma":
                return self.dma.read(addr - DMA_BASE)
            if kind == "intc":
                return self.intc.read(addr - INTC_BASE)
            if kind == "perf":
                return self.perf.read(addr - PERF_BASE)
        except BusError:
            self.perf.count_stall()
            raise
        self.perf.count_stall()
        raise BusError(f"bus: invalid read address 0x{addr:08X}")

    def write(self, addr: int, value: int) -> int:
        """Returns peripheral status where relevant (e.g. UART TX: 0 ok)."""
        if addr % 4 != 0:
            self.perf.count_stall()
            raise BusError(f"bus: unaligned write 0x{addr:08X}")
        self.perf.count_mem()
        value &= 0xFFFFFFFF
        kind = self._route(addr)
        try:
            if kind == "rom":
                self.rom.write_word(addr, value)
                return 0
            if kind == "sram":
                self.sram.write_word(addr, value)
                return 0
            if kind == "uart":
                return self.uart.write(addr - UART_BASE, value)
            if kind == "timer":
                self.timer.write(addr - TIMER_BASE, value)
                return 0
            if kind == "dma":
                self.dma.write(addr - DMA_BASE, value)
                return 0
            if kind == "intc":
                self.intc.write(addr - INTC_BASE, value)
                return 0
            if kind == "perf":
                self.perf.write(addr - PERF_BASE, value)
                return 0
        except BusError:
            self.perf.count_stall()
            raise
        self.perf.count_stall()
        raise BusError(f"bus: invalid write address 0x{addr:08X}")

    # -- stepping --
    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.ticks += 1
            self.perf.tick()
            self.uart.step()
            self.timer.step()
            self.dma.step()

    def run_until(self, predicate, max_ticks: int = 100000) -> int:
        """Step until predicate() is True; returns ticks elapsed. Raises TimeoutError."""
        elapsed = 0
        while elapsed < max_ticks:
            if predicate():
                return elapsed
            self.step(1)
            elapsed += 1
        if predicate():
            return elapsed
        raise TimeoutError(f"run_until timed out after {max_ticks} ticks")

    # -- boot --
    def boot(self, rom_words: list[int] | None = None) -> dict:
        """Model Reset->ROM->stack->.data/.bss->main. Returns measurements."""
        self.ticks = 0
        self.trace = []
        self.cpu.reset()
        self.reset_peripherals()
        self.perf.reset_counters()
        self.perf.enabled = True
        self.perf.ctrl = 0x1
        if rom_words:
            # Bypass ROM readonly for initial load.
            self.rom.data = bytearray(len(self.rom.data))
            self.rom.load_words(rom_words)
        self.sram.zero()
        self.trace.append((self.ticks, "reset"))
        self.step(BOOT_TICKS)
        self.cpu.enter_main()
        self.trace.append((self.ticks, "main_entry"))
        return {
            "boot_ticks": self.ticks,
            "cpu_frequency_mhz": self.config.get("cpu_frequency_mhz", 100),
            "boot_ns": int(self.ticks * 1000 / self.config.get("cpu_frequency_mhz", 100)),
        }

    # -- SRAM helpers for tests --
    def sram_write_word(self, addr: int, value: int) -> None:
        self.write(addr, value)

    def sram_read_word(self, addr: int) -> int:
        return self.read(addr)
