cmake_minimum_required(VERSION 3.16)
project(vlab_soc_c C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_compile_options(-Wall -Wextra -Werror)

add_library(vlab_soc_c STATIC
  src/soc_cpu.c
  src/soc_memory.c
  src/soc_perf.c
  src/soc_intc.c
  src/soc_uart.c
  src/soc_timer.c
  src/soc_dma.c
  src/soc.c
  src/soc_faults.c
  src/host_bridge.c
)
target_include_directories(vlab_soc_c PUBLIC include)

enable_testing()

function(vlab_soc_test name src)
  add_executable(${name} ${src})
  target_link_libraries(${name} PRIVATE vlab_soc_c)
  target_include_directories(${name} PRIVATE include)
  add_test(NAME ${name} COMMAND ${name})
endfunction()

vlab_soc_test(soc_c_boot tests/test_boot.c)
vlab_soc_test(soc_c_bus_errors tests/test_bus_errors.c)
vlab_soc_test(soc_c_dma tests/test_dma.c)
vlab_soc_test(soc_c_dma_burst tests/test_dma_burst.c)
vlab_soc_test(soc_c_intc tests/test_intc.c)
vlab_soc_test(soc_c_timer_uart tests/test_timer_uart.c)
vlab_soc_test(soc_c_faults tests/test_faults.c)
vlab_soc_test(soc_c_regions tests/test_regions.c)
vlab_soc_test(soc_c_endpoints tests/test_endpoints.c)

# Firmware+model link: real drivers on the real model (no mmio.c shim).
add_executable(soc_c_firmware_link tests/test_firmware_link.c
  ../firmware/drivers/uart/uart.c
  ../firmware/drivers/timer/timer.c
  ../firmware/drivers/intc/intc.c
  ../firmware/drivers/dma/dma.c
  ../firmware/platforms/vlab/platform_vlab.c
  ../firmware/hal/hal.c
  ../firmware/hal/host.c
)
target_link_libraries(soc_c_firmware_link PRIVATE vlab_soc_c)
target_include_directories(soc_c_firmware_link PRIVATE include ../firmware/include ../firmware)
target_compile_definitions(soc_c_firmware_link PRIVATE VLAB_HOST_SIM)
add_test(NAME soc_c_firmware_link COMMAND soc_c_firmware_link)

add_executable(soc_c_boot_time bench/boot_time.c)
target_link_libraries(soc_c_boot_time PRIVATE vlab_soc_c)
target_include_directories(soc_c_boot_time PRIVATE include)

add_executable(soc_c_cpu_vs_dma bench/cpu_vs_dma.c)
target_link_libraries(soc_c_cpu_vs_dma PRIVATE vlab_soc_c)
target_include_directories(soc_c_cpu_vs_dma PRIVATE include)
