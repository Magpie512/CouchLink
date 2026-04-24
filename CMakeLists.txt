cmake_minimum_required(VERSION 3.16)
project(CouchLink CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Output directory ─────────────────────────────────────────────
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

# ── Compiler flags ───────────────────────────────────────────────
if(MSVC)
    add_compile_options(/O2 /W3)
else()
    add_compile_options(-O2 -Wall -Wextra)
endif()

# ── Platform-specific system libraries ──────────────────────────
set(PLATFORM_LIBS "")

if(WIN32)
    list(APPEND PLATFORM_LIBS ws2_32 xinput)
    # If ViGEm SDK is present, link it for gamepad injection:
    # find_library(VIGEM_LIB ViGEmClient)
    # if(VIGEM_LIB)
    #     list(APPEND PLATFORM_LIBS ${VIGEM_LIB})
    #     add_compile_definitions(COUCHLINK_VIGEM)
    # endif()

elseif(APPLE)
    find_library(APPSERVICES ApplicationServices REQUIRED)
    find_library(IOKIT       IOKit       REQUIRED)
    find_library(COREFOUND   CoreFoundation REQUIRED)
    list(APPEND PLATFORM_LIBS ${APPSERVICES} ${IOKIT} ${COREFOUND})

else() # Linux
    # uinput is header-only; no extra link needed.
    # pthreads
    find_package(Threads REQUIRED)
    list(APPEND PLATFORM_LIBS Threads::Threads)
endif()

# ── Include path (headers live in core/) ────────────────────────
include_directories(${CMAKE_SOURCE_DIR}/core)

# ── Targets ──────────────────────────────────────────────────────
add_executable(couchlink_host       host/main.cpp)
add_executable(couchlink_controller controller/main.cpp)

target_link_libraries(couchlink_host       PRIVATE ${PLATFORM_LIBS})
target_link_libraries(couchlink_controller PRIVATE ${PLATFORM_LIBS})

# ── Install ──────────────────────────────────────────────────────
install(TARGETS couchlink_host couchlink_controller
        RUNTIME DESTINATION bin)
install(FILES ${CMAKE_SOURCE_DIR}/couchlink.py
              ${CMAKE_SOURCE_DIR}/relay/couchlink_relay.py
        DESTINATION bin)
