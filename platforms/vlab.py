"""CURRENT VLAB PLATFORM: the concrete configuration under test.

GENERAL CONCEPTS used here (defined in soc/memory.py, soc/dma_caps.py):
memory-region tables, DMA capability structs, IRQ maps.
PLATFORM CONFIGURATION (this module): the actual VLAB addresses,
capabilities, and IRQ assignments. Nothing else in the codebase may
duplicate these numbers; import them from here.
"""
from __future__ import annotations

from soc.memory import MemoryRegion, default_regions
from soc.peripherals.dma.caps import DmaCaps

# -- memory map --
ROM_BASE = 0x00000000
SRAM_BASE = 0x10000000
UART_BASE = 0x20000000
TIMER_BASE = 0x20001000
DMA_BASE = 0x20002000
INTC_BASE = 0x20003000
PERF_BASE = 0x20004000
REGION_SIZE = 0x1000

BOOT_TICKS = 5  # Reset -> ROM -> stack -> .data/.bss -> main

# -- IRQ map: line assignment + fixed priority, highest first --
IRQ_UART = 0
IRQ_TIMER = 1
IRQ_DMA = 2
IRQ_NONE = 0xFFFFFFFF
N_LINES = 3
PRIORITY_ORDER = (IRQ_TIMER, IRQ_DMA, IRQ_UART)


def vlab_regions(rom_size: int = 16384,
                 sram_size: int = 65536) -> list[MemoryRegion]:
    """VLAB memory map as a region table (ROM + SRAM + MMIO windows)."""
    return default_regions(
        ROM_BASE, rom_size, SRAM_BASE, sram_size,
        [("uart", UART_BASE, REGION_SIZE),
         ("timer", TIMER_BASE, REGION_SIZE),
         ("dma", DMA_BASE, REGION_SIZE),
         ("intc", INTC_BASE, REGION_SIZE),
         ("perf", PERF_BASE, REGION_SIZE)],
    )


def vlab_dma_caps(max_transfer: int | None = 16384) -> DmaCaps:
    """VLAB DMA capabilities: SRAM-only, 4-byte aligned, IRQ, no cancel."""
    return DmaCaps(
        alignment=4,
        max_transfer=max_transfer,
        supports_ram_to_ram=True,
        supports_mem_to_periph=False,
        supports_periph_to_mem=False,
        supports_interrupts=True,
        supports_cancel=False,
    )


def vlab_irq_map() -> dict:
    """VLAB IRQ assignment (line numbers + priority order)."""
    return {"uart": IRQ_UART, "timer": IRQ_TIMER, "dma": IRQ_DMA,
            "none": IRQ_NONE, "n_lines": N_LINES,
            "priority": PRIORITY_ORDER}
