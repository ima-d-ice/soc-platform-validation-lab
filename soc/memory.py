"""Byte-addressable backing stores + generic memory-region abstraction.

GENERAL CONCEPT: a memory map is a table of regions (base/size/type/
permissions) plus range helpers. PLATFORM CONFIGURATION: which regions
exist (the VLAB map is built by default_regions(); other platforms supply
their own table). SimpleMemory stays the backing store behind one region.
"""
from __future__ import annotations

from dataclasses import dataclass

from .bus import BusError

# Region types (general vocabulary; a platform uses the subset it has).
ROM = "ROM"
SRAM = "SRAM"
DRAM = "DRAM"
MMIO = "MMIO"
PERIPHERAL = "PERIPHERAL"

# Permission bits.
PERM_R = 0x4
PERM_W = 0x2
PERM_X = 0x1

_ADDR_MASK = 0xFFFFFFFF


@dataclass(frozen=True)
class MemoryRegion:
    """One entry of a platform memory map."""

    name: str  # routing key, e.g. "rom", "sram", "uart"
    base: int
    size: int
    type: str  # one of ROM/SRAM/DRAM/MMIO/PERIPHERAL
    perms: int  # PERM_R|PERM_W|PERM_X


def memory_region_contains(region: MemoryRegion, addr: int, length: int = 1) -> bool:
    """True if [addr, addr+length) lies fully inside the region."""
    if length <= 0:
        return False
    if memory_range_overflows(addr, length):
        return False
    return region.base <= addr and addr + length <= region.base + region.size


def memory_range_valid(region: MemoryRegion, addr: int, length: int) -> bool:
    """Usable range check: contained with nonzero length."""
    return length > 0 and memory_region_contains(region, addr, length)


def memory_range_overflows(addr: int, length: int) -> bool:
    """True if addr+length wraps past the 32-bit address space."""
    if length < 0:
        return True
    return addr + length > _ADDR_MASK + 1 or addr < 0


def memory_range_overlaps(a_base: int, a_len: int, b_base: int, b_len: int) -> bool:
    """True if the two byte ranges share at least one address."""
    if a_len <= 0 or b_len <= 0:
        return False
    return a_base < b_base + b_len and b_base < a_base + a_len


def default_regions(rom_base: int, rom_size: int, sram_base: int, sram_size: int,
                    mmio_windows: list[tuple[str, int, int]] | None = None) -> list[MemoryRegion]:
    """CURRENT VLAB PLATFORM: ROM + SRAM + MMIO windows as a region table."""
    regions = [
        MemoryRegion("rom", rom_base, rom_size, ROM, PERM_R | PERM_X),
        MemoryRegion("sram", sram_base, sram_size, SRAM, PERM_R | PERM_W),
    ]
    for name, base, size in mmio_windows or []:
        regions.append(MemoryRegion(name, base, size, MMIO, PERM_R | PERM_W))
    return regions


def find_region(regions: list[MemoryRegion], addr: int, length: int = 1) -> MemoryRegion | None:
    """First region containing [addr, addr+length), or None."""
    for region in regions:
        if memory_region_contains(region, addr, length):
            return region
    return None


class SimpleMemory:
    """Flat bytearray with word helpers. ROM enforces read-only at run time."""

    def __init__(self, base: int, size: int, *, readonly: bool = False, name: str = "mem"):
        self.base = base
        self.size = size
        self.readonly = readonly
        self.name = name
        self.data = bytearray(size)

    def contains(self, addr: int, length: int = 4) -> bool:
        return self.base <= addr and addr + length <= self.base + self.size

    def _offset(self, addr: int, length: int = 4) -> int:
        if not self.contains(addr, length):
            raise BusError(f"{self.name}: address 0x{addr:08X} out of range")
        return addr - self.base

    def read_word(self, addr: int) -> int:
        if addr % 4 != 0:
            raise BusError(f"{self.name}: unaligned read 0x{addr:08X}")
        off = self._offset(addr, 4)
        return int.from_bytes(self.data[off : off + 4], "little")

    def write_word(self, addr: int, value: int) -> None:
        if addr % 4 != 0:
            raise BusError(f"{self.name}: unaligned write 0x{addr:08X}")
        if self.readonly:
            raise BusError(f"{self.name}: write to read-only region 0x{addr:08X}")
        off = self._offset(addr, 4)
        self.data[off : off + 4] = (value & 0xFFFFFFFF).to_bytes(4, "little")

    def read_bytes(self, addr: int, length: int) -> bytes:
        off = self._offset(addr, length)
        return bytes(self.data[off : off + length])

    def write_bytes(self, addr: int, payload: bytes) -> None:
        if self.readonly:
            raise BusError(f"{self.name}: write to read-only region 0x{addr:08X}")
        off = self._offset(addr, len(payload))
        self.data[off : off + len(payload)] = payload

    def load_words(self, words: list[int]) -> None:
        """Load image into memory (bypasses readonly for initial boot load)."""
        for i, w in enumerate(words):
            off = i * 4
            if off + 4 > self.size:
                raise BusError(f"{self.name}: image too large")
            self.data[off : off + 4] = (w & 0xFFFFFFFF).to_bytes(4, "little")

    def zero(self) -> None:
        for i in range(len(self.data)):
            self.data[i] = 0
