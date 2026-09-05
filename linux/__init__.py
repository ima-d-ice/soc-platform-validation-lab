"""linux/: userspace platform model of Linux-facing device interaction.

Explicitly NOT a kernel driver: this code runs in the host Python process
and models the layering a platform driver would implement (application API
-> driver abstraction -> MMIO layer -> virtual device) against the virtual
SoC. See docs/linux-platform.md for what is virtual/measured/modeled and
what would change on real Linux hardware.
"""
from .app import StreamApp
from .driver import StreamDriver, StreamError
from .mmio import DeviceRegs

__all__ = ["DeviceRegs", "StreamApp", "StreamDriver", "StreamError"]
