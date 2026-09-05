"""platforms: concrete platform configurations (PLATFORM CONFIGURATION).

Each module in this package describes one complete platform: its memory
map, DMA capabilities, and IRQ map. Generic code (soc/, firmware/) consumes
these tables; nothing outside platforms/ may hard-code VLAB addresses,
capabilities, or IRQ assignments.
"""
