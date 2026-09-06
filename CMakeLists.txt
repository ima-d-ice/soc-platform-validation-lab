# vlab-soc: one root build for the model, firmware, tests, and benches.
#
#   cmake -S . -B build
#   cmake --build build
#   ctest --test-dir build --output-on-failure
cmake_minimum_required(VERSION 3.16)
project(vlab_soc C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_compile_options(-Wall -Wextra -Werror)

enable_testing()

# ---- virtual SoC model (CPU/bus/memory/peripherals) + platform data ----
add_library(soc_model STATIC
  soc_c/src/soc_cpu.c
  soc_c/src/soc_memory.c
  soc_c/src/bus.c
  soc_c/src/soc_perf.c
  soc_c/src/soc_intc.c
  soc_c/src/soc_uart.c
  soc_c/src/soc_timer.c
  soc_c/src/soc_dma.c
  soc_c/src/soc.c
  soc_c/src/host_bridge.c
  # Single platform table: map, caps, DMA FIFOs, IRQ map.
  firmware/platform/platform_vlab.c
)
target_include_directories(soc_model PUBLIC soc_c/include firmware/include)
target_include_directories(soc_model PRIVATE firmware)

# ---- firmware (drivers + HAL, host backend into the live model) ----
add_library(vlab_firmware STATIC
  firmware/hal/hal.c
  firmware/hal/host.c
  firmware/drivers/uart.c
  firmware/drivers/timer.c
  firmware/drivers/intc.c
  firmware/drivers/dma.c
  firmware/isr/isr.c
  firmware/platform/platform_init.c
)
target_include_directories(vlab_firmware PUBLIC firmware/include)
target_include_directories(vlab_firmware PRIVATE firmware)
target_link_libraries(vlab_firmware PUBLIC soc_model)

# ---- tests: one helper, every suite links both libraries ----
function(vlab_test name)
  add_executable(${name} ${ARGN})
  target_link_libraries(${name} PRIVATE vlab_firmware soc_model)
  target_include_directories(${name} PRIVATE firmware/include firmware soc_c/include)
  add_test(NAME ${name} COMMAND ${name})
endfunction()

# Model: boot, bus/decode, DMA matrix, interrupts, timer+UART, faults.
vlab_test(test_boot soc_c/tests/test_boot.c)
vlab_test(test_bus_errors soc_c/tests/test_bus_errors.c)
vlab_test(test_endpoints soc_c/tests/test_endpoints.c)
vlab_test(test_intc soc_c/tests/test_intc.c)
vlab_test(test_timer_uart soc_c/tests/test_timer_uart.c)
vlab_test(test_faults soc_c/tests/test_faults.c)
# Integration: real drivers on the live model (incl. demo legs).
vlab_test(test_firmware_link soc_c/tests/test_firmware_link.c)
# Firmware: HAL, regions, caps, drivers, ISR dispatch, DMA, faults.
vlab_test(test_hal firmware/tests/unit/test_hal.c)
vlab_test(test_mem_regions firmware/tests/unit/test_mem_regions.c)
vlab_test(test_dma_caps firmware/tests/unit/test_dma_caps.c)
vlab_test(test_drivers firmware/tests/unit/test_drivers.c)
vlab_test(test_isr firmware/tests/integration/test_isr.c)
vlab_test(test_dma_integration firmware/tests/integration/test_dma_endpoints.c)
vlab_test(test_dma_faults firmware/tests/fault/test_dma_faults.c)

# ---- application + smoke ----
add_executable(firmware firmware/apps/main.c)
target_link_libraries(firmware PRIVATE vlab_firmware soc_model)
target_include_directories(firmware PRIVATE firmware/include firmware soc_c/include)
add_test(NAME firmware_smoke COMMAND firmware)

# ---- benchmarks (CSV/JSON metrics to stdout) ----
add_executable(bench_boot soc_c/bench/boot_time.c)
target_link_libraries(bench_boot PRIVATE soc_model)
target_include_directories(bench_boot PRIVATE soc_c/include)

add_executable(bench_dma soc_c/bench/cpu_vs_dma.c)
target_link_libraries(bench_dma PRIVATE soc_model)
target_include_directories(bench_dma PRIVATE soc_c/include)
