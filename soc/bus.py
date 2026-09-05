"""Bus errors for illegal MMIO/memory accesses."""
from __future__ import annotations


class BusError(Exception):
    """Raised on invalid address, permission violation, or unaligned access."""
