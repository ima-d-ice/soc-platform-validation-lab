cmake_minimum_required(VERSION 3.16)
project(vlab_firmware C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_compile_options(-Wall -Wextra -Werror)

# soc_regs.h is frozen in-tree; ensure it exists before configuring.
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/include/soc_regs.h")
  message(FATAL_ERROR
    "Missing include/soc_regs.h (frozen spec header, do not hand-edit).")
endif()

add_library(vlab_drivers STATIC
  drivers/mmio.c
  hal/hal.c
  drivers/uart/uart.c
  drivers/timer/timer.c
  drivers/intc/intc.c
  drivers/dma/dma.c
  isr/isr.c
  platforms/vlab/platform_vlab.c
  boot/boot.c
)
# HAL backend split: exactly one backend links. Host builds use the
# simulation backend; silicon (freestanding) builds use volatile MMIO.
option(VLAB_HOST_SIM "Route HAL through the host bus shim" ON)
if(VLAB_HOST_SIM)
  target_sources(vlab_drivers PRIVATE hal/host.c)
  target_compile_definitions(vlab_drivers PUBLIC VLAB_HOST_SIM)
else()
  target_sources(vlab_drivers PRIVATE hal/silicon.c)
endif()
# Public headers (driver API, HAL, ISR, caps, regions, generated regs);
# the firmware root itself is private so drivers reach platforms/ data.
target_include_directories(vlab_drivers PUBLIC include PRIVATE .)

add_executable(firmware apps/main.c)
target_link_libraries(firmware PRIVATE vlab_drivers)

add_executable(isr_demo apps/isr_demo.c)
target_link_libraries(isr_demo PRIVATE vlab_drivers)

enable_testing()
add_test(NAME firmware_smoke COMMAND firmware)
add_test(NAME isr_demo_fw COMMAND isr_demo)
set_tests_properties(isr_demo_fw PROPERTIES PASS_REGULAR_EXPRESSION "DEMO OK")

function(vlab_test name src)
  add_executable(${name} ${src})
  target_link_libraries(${name} PRIVATE vlab_drivers)
  add_test(NAME ${name} COMMAND ${name})
endfunction()

# Unit: pure logic, one module at a time.
vlab_test(hal_unit tests/unit/test_hal.c)
vlab_test(drivers_unit tests/unit/test_drivers.c)
vlab_test(mem_regions_unit tests/unit/test_mem_regions.c)
vlab_test(dma_caps_unit tests/unit/test_dma_caps.c)
# Integration: driver + ISR + platform wiring.
vlab_test(isr_unit tests/integration/test_isr.c)
vlab_test(dma_platform_integration tests/integration/test_dma_platform.c)
vlab_test(dma_endpoints tests/integration/test_dma_endpoints.c)
# Fault: invalid use, error latch, recovery.
vlab_test(dma_faults tests/fault/test_dma_faults.c)
