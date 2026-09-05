"""Boot validation: reset -> ROM -> startup -> main."""
from __future__ import annotations

from soc.soc import BOOT_TICKS, ROM_BASE, SRAM_BASE


def test_boot_succeeds(fresh_soc):
    info = fresh_soc.boot(rom_words=[0x12345678, 0x9ABCDEF0])
    assert fresh_soc.cpu.running is True
    assert fresh_soc.cpu.pc == ROM_BASE
    assert fresh_soc.cpu.sp == SRAM_BASE + fresh_soc.config["sram_size_bytes"]
    assert info["boot_ticks"] == BOOT_TICKS == 5
    assert fresh_soc.ticks == BOOT_TICKS
    assert fresh_soc.trace[-1][1] == "main_entry"
    # ROM image landed.
    assert fresh_soc.read(ROM_BASE) == 0x12345678
    # PERF enabled and counting real ticks.
    assert fresh_soc.perf.enabled is True
    assert fresh_soc.perf.cycles == BOOT_TICKS


def test_bss_zeroed_on_boot(soc):
    # Booted fixture zeroes SRAM.
    assert soc.sram_read_word(SRAM_BASE) == 0
    assert soc.sram_read_word(SRAM_BASE + 0x100) == 0
    # Dirty then reboot -> zero again.
    soc.sram_write_word(SRAM_BASE, 0xDEADBEEF)
    assert soc.sram_read_word(SRAM_BASE) == 0xDEADBEEF
    soc.boot()
    assert soc.sram_read_word(SRAM_BASE) == 0


def test_boot_time_deterministic(fresh_soc):
    first = fresh_soc.boot()
    second = fresh_soc.boot()
    assert first["boot_ticks"] == second["boot_ticks"]
    mhz = fresh_soc.config["cpu_frequency_mhz"]
    assert first["boot_ns"] == first["boot_ticks"] * 1000 // mhz
