"""Byte-addressable ROM/SRAM backing stores."""
from __future__ import annotations

from .bus import BusError


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
