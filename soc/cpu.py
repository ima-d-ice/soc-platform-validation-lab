"""Minimal CPU model: reset/halt/run state, PC/SP, tick accounting."""
from __future__ import annotations


class Cpu:
    def __init__(self, rom_base: int, sram_top: int):
        self.rom_base = rom_base
        self.sram_top = sram_top
        self.pc = rom_base
        self.sp = sram_top
        self.running = False
        self.boot_ticks = 0

    def reset(self) -> None:
        self.pc = self.rom_base
        self.sp = self.sram_top
        self.running = False
        self.boot_ticks = 0

    def enter_main(self) -> None:
        self.running = True
