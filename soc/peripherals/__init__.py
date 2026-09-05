"""soc.peripherals: memory-mapped peripheral models (UART/timer/DMA/INTC/PERF).

Each subpackage owns one peripheral's registers, behavior, and timing.
Shared concepts (regions, DMA caps) live in soc/memory and
soc/peripherals/dma/caps.py. Interrupt lines and priorities belong to the
platform configuration (platforms/vlab.py), not to these models.
"""
