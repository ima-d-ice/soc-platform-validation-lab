"""Unit tests for the generic memory-region helpers (GENERAL CONCEPT).

These tests use synthetic maps (including DRAM, which VLAB does not have)
to prove the helpers are independent of any platform's assumptions.
"""
from __future__ import annotations

from soc.memory import (
    DRAM,
    MMIO,
    PERM_R,
    PERM_W,
    PERM_X,
    ROM,
    SRAM,
    MemoryRegion,
    default_regions,
    find_region,
    memory_range_overflows,
    memory_range_overlaps,
    memory_range_valid,
    memory_region_contains,
)

ROM_BASE, SRAM_BASE = 0x00000000, 0x10000000


def _vlab():
    return default_regions(ROM_BASE, 16384, SRAM_BASE, 65536,
                           [("uart", 0x20000000, 0x1000)])


def test_region_contains_edges():
    regions = _vlab()
    sram = next(r for r in regions if r.name == "sram")
    assert memory_region_contains(sram, SRAM_BASE, 4)
    assert memory_region_contains(sram, SRAM_BASE + 65536 - 4, 4)
    assert not memory_region_contains(sram, SRAM_BASE + 65536 - 3, 4)
    assert not memory_region_contains(sram, SRAM_BASE, 0)
    assert not memory_region_contains(sram, 0x20000000, 4)


def test_range_valid_and_perms():
    regions = _vlab()
    rom = next(r for r in regions if r.name == "rom")
    assert rom.type == ROM and rom.perms & PERM_R and not rom.perms & PERM_W
    assert memory_range_valid(rom, ROM_BASE, 4)
    assert not memory_range_valid(rom, ROM_BASE, 0)


def test_overflow_wrapping():
    assert memory_range_overflows(0xFFFFFFFF, 4)
    assert memory_range_overflows(0xFFFFFFFC, 5)
    assert not memory_range_overflows(0xFFFFFFFC, 4)
    assert not memory_range_overflows(SRAM_BASE, 65536)
    assert memory_range_overflows(0x100, -1)


def test_overlap_cases():
    assert memory_range_overlaps(0x1000, 0x100, 0x1050, 0x100)
    assert memory_range_overlaps(0x1050, 0x100, 0x1000, 0x100)
    assert not memory_range_overlaps(0x1000, 0x100, 0x1100, 0x100)  # adjacent
    assert not memory_range_overlaps(0x1000, 0, 0x1000, 0x100)
    assert not memory_range_overlaps(0x1000, 0x100, 0x1000, 0)


def test_dram_region_is_first_class():
    """A non-VLAB map with DRAM behaves identically (platform-independent)."""
    regions = [MemoryRegion("dram", 0x40000000, 0x100000, DRAM,
                            PERM_R | PERM_W | PERM_X)]
    found = find_region(regions, 0x40000FFC, 4)
    assert found is not None and found.type == DRAM
    assert find_region(regions, SRAM_BASE, 4) is None
    assert memory_range_valid(found, 0x40000000, 0x100000)


def test_find_region_vlab_map():
    regions = _vlab()
    assert find_region(regions, ROM_BASE, 4).name == "rom"
    assert find_region(regions, SRAM_BASE, 4).name == "sram"
    assert find_region(regions, 0x20000000, 1).name == "uart"
    assert find_region(regions, 0x30000000, 4) is None
