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
  drivers/uart.c
  drivers/timer.c
  drivers/intc.c
  drivers/dma.c
  boot/boot.c
)
target_include_directories(vlab_drivers PUBLIC include)

add_executable(firmware apps/main.c)
target_link_libraries(firmware PRIVATE vlab_drivers)

enable_testing()
add_test(NAME firmware_smoke COMMAND firmware)
