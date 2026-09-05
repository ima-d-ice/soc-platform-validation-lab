cmake_minimum_required(VERSION 3.16)
project(vlab_firmware C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_compile_options(-Wall -Wextra -Werror)

# soc_regs.h is generated; ensure it exists before configuring.
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/include/soc_regs.h")
  message(FATAL_ERROR
    "Missing include/soc_regs.h. Run: python3 tools/reggen.py from repo root.")
endif()

add_library(vlab_drivers STATIC
  drivers/mmio.c
  hal/hal.c
  drivers/uart.c
  drivers/timer.c
  drivers/intc.c
  drivers/dma.c
  isr/isr.c
  boot/boot.c
)
target_include_directories(vlab_drivers PUBLIC include)

# Host simulation: MMIO routes to the shim; silicon builds unset this and
# use volatile pointer dereferences in hal/hal.c.
target_compile_definitions(vlab_drivers PUBLIC VLAB_HOST_SIM)

add_executable(firmware apps/main.c)
target_link_libraries(firmware PRIVATE vlab_drivers)

add_executable(isr_demo apps/isr_demo.c)
target_link_libraries(isr_demo PRIVATE vlab_drivers)

enable_testing()
add_test(NAME firmware_smoke COMMAND firmware)
add_test(NAME isr_demo_fw COMMAND isr_demo)
set_tests_properties(isr_demo_fw PROPERTIES PASS_REGULAR_EXPRESSION "DEMO OK")

add_executable(test_hal tests/test_hal.c)
target_link_libraries(test_hal PRIVATE vlab_drivers)
add_test(NAME hal_unit COMMAND test_hal)

add_executable(test_drivers tests/test_drivers.c)
target_link_libraries(test_drivers PRIVATE vlab_drivers)
add_test(NAME drivers_unit COMMAND test_drivers)

add_executable(test_isr tests/test_isr.c)
target_link_libraries(test_isr PRIVATE vlab_drivers)
add_test(NAME isr_unit COMMAND test_isr)
