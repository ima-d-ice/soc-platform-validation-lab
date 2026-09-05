"""Generic DMA capability model (GENERAL CONCEPT).

GENERAL: a DMA implementation supports an address-type matrix over a
platform's memory map, an alignment, a max transfer, and optional
features (interrupts, cancel). PLATFORM CONFIGURATION: the concrete
DmaCaps + region table (see platforms/vlab.py for the VLAB instance).

Error split (tested explicitly):
- invalid DMA driver API use -> ERR_LEN / ERR_ALIGN / ERR_ADDR
  (bad length multiple, misaligned, unmapped/overflowed address).
- unsupported by platform -> ERR_UNSUPPORTED (address valid but the
  region type or direction is outside this DMA's capabilities, or the
  length exceeds max_transfer).
"""
from __future__ import annotations

from dataclasses import dataclass

from ...memory import DRAM, MMIO, PERIPHERAL, SRAM, MemoryRegion, find_region

# Endpoint address types from the DMA's point of view.
DMA_MEM = "MEM"
DMA_PERIPHERAL = "PERIPHERAL"
DMA_DEVICE = "DEVICE"

# RAM-like region types usable as MEM endpoints.
_MEM_TYPES = (SRAM, DRAM)
# Register-style region types usable as PERIPHERAL/DEVICE endpoints.
_PERIPH_TYPES = (MMIO, PERIPHERAL)

ERR_UNSUPPORTED = 4


@dataclass(frozen=True)
class DmaCaps:
    """What one DMA implementation supports (platform data, not logic)."""

    alignment: int = 4
    max_transfer: int | None = None  # bytes; None = unlimited
    supports_ram_to_ram: bool = True
    supports_mem_to_periph: bool = False
    supports_periph_to_mem: bool = False
    supports_interrupts: bool = True
    supports_cancel: bool = False


def endpoint_type(regions: list[MemoryRegion], addr: int, length: int) -> str | None:
    """Classify one transfer endpoint; None if unmapped/overflowing."""
    region = find_region(regions, addr, length)
    if region is None:
        return None
    if region.type in _MEM_TYPES:
        return DMA_MEM
    if region.type in _PERIPH_TYPES:
        return DMA_PERIPHERAL
    return DMA_DEVICE


def dma_address_valid(regions: list[MemoryRegion], caps: DmaCaps,
                      addr: int, length: int, type: str) -> bool:
    """True if [addr, addr+length) is a usable endpoint of the given type."""
    if length <= 0:
        return False
    if caps.alignment > 1 and (addr % caps.alignment != 0
                               or length % caps.alignment != 0):
        return False
    actual = endpoint_type(regions, addr, length)
    if actual is None:
        return False
    if type == DMA_MEM:
        return actual == DMA_MEM
    if type == DMA_PERIPHERAL:
        return actual in (DMA_PERIPHERAL, DMA_DEVICE)
    if type == DMA_DEVICE:
        return actual == DMA_DEVICE
    return False


def dma_direction_supported(caps: DmaCaps, src_type: str, dst_type: str) -> bool:
    """True if the (src, dst) type pair is within this DMA's capabilities."""
    if src_type == DMA_MEM and dst_type == DMA_MEM:
        return caps.supports_ram_to_ram
    if src_type == DMA_MEM and dst_type in (DMA_PERIPHERAL, DMA_DEVICE):
        return caps.supports_mem_to_periph
    if src_type in (DMA_PERIPHERAL, DMA_DEVICE) and dst_type == DMA_MEM:
        return caps.supports_periph_to_mem
    return False
