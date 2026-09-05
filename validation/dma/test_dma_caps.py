"""Generalized DMA capability tests (GENERAL CONCEPT, platform-independent).

These construct Dma directly against synthetic maps (including DRAM, which
VLAB does not have) to prove validation depends on caps + regions, not on
VLAB's SRAM-only assumptions. Error split under test:
- invalid driver-API use -> ERR_LEN / ERR_ALIGN / ERR_ADDR
- unsupported by platform -> ERR_UNSUPPORTED (mapped but disallowed type,
  direction, or over max_transfer)
"""
from __future__ import annotations

import pytest

from soc.bus import BusError
from soc.peripherals.dma import (STATUS_BUSY as BUSY, STATUS_DONE as DONE,
                                 Dma, STATUS_ERROR as ERROR, ERR_ADDR,
                                 ERR_ALIGN, ERR_LEN, ERR_UNSUPPORTED)
from soc.peripherals.dma.caps import (DMA_DEVICE, DMA_MEM, DMA_PERIPHERAL,
                                      DmaCaps, dma_address_valid,
                                      dma_direction_supported,
                                      endpoint_type)
from soc.memory import (DRAM, MMIO, PERM_R, PERM_W, SRAM, MemoryRegion)

SRAM_BASE = 0x10000000
DRAM_BASE = 0x40000000
PERIPH_BASE = 0x20002000


class MemHarness:
    """Byte stores keyed by base address, backing custom DMA bridges."""

    def __init__(self):
        self.stores: dict[int, bytearray] = {}

    def add(self, base: int, size: int):
        self.stores[base] = bytearray(size)

    def _locate(self, addr: int, length: int):
        for base, mem in self.stores.items():
            if base <= addr and addr + length <= base + len(mem):
                return mem, addr - base
        raise BusError(f"test store: 0x{addr:08X} unmapped")

    def reader(self, addr: int, length: int) -> bytes:
        mem, off = self._locate(addr, length)
        return bytes(mem[off:off + length])

    def writer(self, addr: int, payload: bytes) -> None:
        mem, off = self._locate(addr, len(payload))
        mem[off:off + len(payload)] = payload


def _regions():
    return [
        MemoryRegion("sram", SRAM_BASE, 0x10000, SRAM, PERM_R | PERM_W),
        MemoryRegion("dram", DRAM_BASE, 0x100000, DRAM, PERM_R | PERM_W),
        MemoryRegion("periph", PERIPH_BASE, 0x1000, MMIO, PERM_R | PERM_W),
    ]


def _dma(regions=None, caps=None, **kw):
    regions = regions if regions is not None else _regions()
    caps = caps if caps is not None else DmaCaps()
    harness = MemHarness()
    harness.add(SRAM_BASE, 0x10000)
    harness.add(DRAM_BASE, 0x100000)
    dma = Dma(sram_base=SRAM_BASE, sram_size=0x10000, regions=regions,
              caps=caps, mem_reader=harness.reader,
              mem_writer=harness.writer, **kw)
    return dma, harness


def _start(dma, src, dst, nbytes, irq_en=False):
    dma.src, dma.dst, dma.length = src, dst, nbytes
    dma.write(0x0C, 0x1 | (0x2 if irq_en else 0))  # CTRL + START
    return dma.read(0x10)  # STATUS


def _run(dma, max_steps=10000):
    """Step a bare Dma until terminal state (BUSY clears)."""
    for _ in range(max_steps):
        if not (dma.read(0x10) & BUSY):
            return
        dma.step()


def test_dram_mem_to_mem():
    """A DRAM region behaves like SRAM when caps allow it (not VLAB)."""
    caps = DmaCaps(supports_ram_to_ram=True)
    dma, harness = _dma(caps=caps)
    for i in range(0, 64, 4):
        harness.stores[DRAM_BASE][i:i + 4] = (0xD0000000 | i).to_bytes(4, "little")
    st = _start(dma, DRAM_BASE, DRAM_BASE + 0x1000, 64)
    assert st & BUSY
    _run(dma)
    assert dma.read(0x10) & DONE
    assert harness.reader(DRAM_BASE + 0x1000, 4) == (0xD0000000).to_bytes(4, "little")


def test_periph_to_mem_with_caps():
    """PERIPH->MEM works when the platform enables that direction."""
    caps = DmaCaps(supports_ram_to_ram=True, supports_periph_to_mem=True)
    dma, harness = _dma(caps=caps)
    harness.add(PERIPH_BASE, 0x1000)
    harness.writer(PERIPH_BASE, b"\xAA\xBB\xCC\xDD" * 4)
    st = _start(dma, PERIPH_BASE, SRAM_BASE, 16)
    assert st & BUSY
    _run(dma)
    assert dma.read(0x10) & DONE
    assert harness.reader(SRAM_BASE, 4) == b"\xAA\xBB\xCC\xDD"


def test_mem_to_periph_with_caps():
    caps = DmaCaps(supports_ram_to_ram=True, supports_mem_to_periph=True)
    dma, harness = _dma(caps=caps)
    harness.add(PERIPH_BASE, 0x1000)
    st = _start(dma, SRAM_BASE, PERIPH_BASE, 16)
    assert st & BUSY
    _run(dma)
    assert dma.read(0x10) & DONE


def test_unsupported_direction_is_distinct_from_invalid():
    """Mapped but disallowed direction -> ERR_UNSUPPORTED, not ERR_ADDR."""
    dma, _ = _dma(caps=DmaCaps())  # default: mem-to-mem only
    _start(dma, SRAM_BASE, PERIPH_BASE, 16)
    assert dma.read(0x10) & ERROR
    assert dma.read(0x18) == ERR_UNSUPPORTED  # NOT ERR_ADDR: it is mapped


def test_invalid_region_is_addr_error():
    dma, _ = _dma()
    _start(dma, 0x30000000, SRAM_BASE, 16)
    assert dma.read(0x10) & ERROR
    assert dma.read(0x18) == ERR_ADDR  # unmapped: invalid use, not platform


def test_overflow_is_addr_error():
    dma, _ = _dma()
    _start(dma, 0xFFFFFFFC, SRAM_BASE, 16)  # wraps past 32-bit space
    assert dma.read(0x10) & ERROR
    assert dma.read(0x18) == ERR_ADDR


def test_max_transfer_is_platform_limit():
    dma, _ = _dma(caps=DmaCaps(max_transfer=64))
    _start(dma, SRAM_BASE, SRAM_BASE + 0x1000, 128)
    assert dma.read(0x10) & ERROR
    assert dma.read(0x18) == ERR_UNSUPPORTED  # valid use, over platform max
    dma.write(0x14, 1)  # IRQ_CLEAR
    _start(dma, SRAM_BASE, SRAM_BASE + 0x1000, 64)
    assert dma.read(0x10) & BUSY  # at the max: fine


def test_alignment_failure_stays_api_error():
    dma, _ = _dma(caps=DmaCaps(alignment=4))
    _start(dma, SRAM_BASE + 1, SRAM_BASE + 0x1000, 16)
    assert dma.read(0x18) == ERR_ALIGN  # invalid use, not platform
    _start(dma, SRAM_BASE, SRAM_BASE + 0x1000, 0)
    assert dma.read(0x18) == ERR_LEN


def test_periph_to_periph_unsupported():
    dma, _ = _dma(caps=DmaCaps(supports_mem_to_periph=True,
                               supports_periph_to_mem=True))
    dma2_regions = _regions() + [MemoryRegion("periph2", 0x20003000, 0x1000,
                                              MMIO, PERM_R | PERM_W)]
    dma.regions = dma2_regions
    _start(dma, PERIPH_BASE, 0x20003000, 16)
    assert dma.read(0x18) == ERR_UNSUPPORTED  # no periph-to-periph flag exists


def test_helpers_directly():
    regions = _vlab_regions = _regions()
    assert endpoint_type(regions, SRAM_BASE, 16) == DMA_MEM
    assert endpoint_type(regions, DRAM_BASE, 16) == DMA_MEM
    assert endpoint_type(regions, PERIPH_BASE, 16) == DMA_PERIPHERAL
    assert endpoint_type(regions, 0x30000000, 16) is None
    assert endpoint_type(regions, 0xFFFFFFFC, 16) is None  # overflow
    caps = DmaCaps()
    assert dma_address_valid(regions, caps, SRAM_BASE, 16, DMA_MEM)
    assert not dma_address_valid(regions, caps, SRAM_BASE + 1, 16, DMA_MEM)
    assert not dma_address_valid(regions, caps, SRAM_BASE, 0, DMA_MEM)
    assert dma_direction_supported(caps, DMA_MEM, DMA_MEM)
    assert not dma_direction_supported(caps, DMA_MEM, DMA_PERIPHERAL)
    assert not dma_direction_supported(caps, "NOPE", DMA_MEM)


def test_vlab_defaults_still_sram_only():
    """Default caps (as SoC builds them for VLAB) preserve old behavior."""
    from platforms.vlab import vlab_dma_caps
    caps = vlab_dma_caps()
    assert caps.alignment == 4 and caps.max_transfer == 16384
    assert caps.supports_ram_to_ram and not caps.supports_mem_to_periph
    assert not caps.supports_periph_to_mem and caps.supports_interrupts
