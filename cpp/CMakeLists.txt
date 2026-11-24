cmake_minimum_required(VERSION 3.18...3.31)
project(quant_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
find_package(Threads REQUIRED)  # the bootstrap runs resamples in parallel

if(MSVC)
  add_compile_options(/W4 /permissive- /O2)
else()
  add_compile_options(-Wall -Wextra -Wpedantic -O3)
endif()

# Python extension: built by scikit-build-core (pip / uv), skipped for a plain CMake build.
if(SKBUILD)
  find_package(Python 3.11 COMPONENTS Interpreter Development.Module REQUIRED)
  execute_process(
    COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT)
  find_package(nanobind CONFIG REQUIRED)
  nanobind_add_module(quant_core NB_STATIC src/bindings.cpp)
  target_include_directories(quant_core PRIVATE include)
  target_link_libraries(quant_core PRIVATE Threads::Threads)
  install(TARGETS quant_core LIBRARY DESTINATION .)
endif()

# C++ unit tests: cmake -S cpp -B build && cmake --build build && ctest --test-dir build
option(QUANT_BUILD_TESTS "Build the C++ unit tests" ON)
if(QUANT_BUILD_TESTS AND NOT SKBUILD)
  enable_testing()
  add_executable(test_risk tests/test_risk.cpp)
  target_include_directories(test_risk PRIVATE include)
  target_link_libraries(test_risk PRIVATE Threads::Threads)
  add_test(NAME risk COMMAND test_risk)
endif()
