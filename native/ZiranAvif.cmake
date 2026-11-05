# Shared decoder policy for package recipes and Linux/Android static consumers.
# Sources are caller-resolved, immutable package checkouts. Nothing is fetched.
include_guard(GLOBAL)

function(_ziran_avif_source name path expected marker)
  if(NOT EXISTS "${path}/${marker}")
    message(FATAL_ERROR "${name}: locked source directory required: ${path}")
  endif()
  execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${path}" rev-parse HEAD
    OUTPUT_VARIABLE actual OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE status)
  if(NOT status EQUAL 0 OR NOT actual STREQUAL expected)
    message(FATAL_ERROR "${name}: source pin mismatch; expected ${expected}, got ${actual}")
  endif()
  execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${path}" status --porcelain
    OUTPUT_VARIABLE dirty RESULT_VARIABLE status)
  if(NOT status EQUAL 0 OR NOT dirty STREQUAL "")
    message(FATAL_ERROR "${name}: source must be clean")
  endif()
endfunction()

# Meson and Ninja build dav1d. ZIRAN_AVIF_TOOLS (cache or environment) names
# a `pip install --target` directory holding both, such as this package's
# build/native-tools; otherwise meson and ninja come from PATH.
function(_ziran_avif_meson output)
  set(tools "${ZIRAN_AVIF_TOOLS}")
  if(tools STREQUAL "")
    set(tools "$ENV{ZIRAN_AVIF_TOOLS}")
  endif()
  get_filename_component(package "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." ABSOLUTE)
  if(tools STREQUAL "" AND EXISTS "${package}/build/native-tools/mesonbuild")
    set(tools "${package}/build/native-tools")
  endif()
  set(path "$ENV{PATH}")
  if(ANDROID_TOOLCHAIN_ROOT)
    set(path "${ANDROID_TOOLCHAIN_ROOT}/bin:${path}")
  endif()
  if(NOT tools STREQUAL "")
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(${output} "${CMAKE_COMMAND}" -E env "PYTHONPATH=${tools}" "PATH=${tools}/bin:${path}"
      "${Python3_EXECUTABLE}" -m mesonbuild.mesonmain PARENT_SCOPE)
    return()
  endif()
  find_program(ZIRAN_AVIF_MESON meson)
  find_program(ZIRAN_AVIF_NINJA NAMES ninja ninja-build)
  if(NOT ZIRAN_AVIF_MESON OR NOT ZIRAN_AVIF_NINJA)
    message(FATAL_ERROR "dav1d needs meson and ninja on PATH, or ZIRAN_AVIF_TOOLS naming a pip --target directory with both")
  endif()
  get_filename_component(ninja_dir "${ZIRAN_AVIF_NINJA}" DIRECTORY)
  set(${output} "${CMAKE_COMMAND}" -E env "PATH=${ninja_dir}:${path}" "${ZIRAN_AVIF_MESON}" PARENT_SCOPE)
endfunction()

function(_ziran_avif_meson_list output)
  set(items)
  foreach(item IN LISTS ARGN)
    list(APPEND items "'${item}'")
  endforeach()
  list(JOIN items ", " joined)
  set(${output} "[${joined}]" PARENT_SCOPE)
endfunction()

# Build pinned dav1d with its hand-written assembly and runtime CPU dispatch
# (x86 SSE2..AVX-512 through NASM, ARMv7/AArch64 NEON through the C
# compiler's assembler). The static archive is an AVIF_LOCAL codec: libavif
# merges it into libavif.a, and the shared bridge links it directly.
function(_ziran_avif_dav1d source)
  include(ExternalProject)
  _ziran_avif_meson(meson)
  set(build "${CMAKE_CURRENT_BINARY_DIR}/dav1d")
  set(install "${CMAKE_CURRENT_BINARY_DIR}/dav1d-install")
  file(MAKE_DIRECTORY "${install}/include")
  set(compiler "${CMAKE_C_COMPILER}")
  if(CMAKE_C_COMPILER_TARGET)
    list(APPEND compiler "--target=${CMAKE_C_COMPILER_TARGET}")
  endif()
  if(CMAKE_SYSROOT)
    list(APPEND compiler "--sysroot=${CMAKE_SYSROOT}")
  endif()
  separate_arguments(flags NATIVE_COMMAND "${CMAKE_C_FLAGS}")
  _ziran_avif_meson_list(c "${compiler}")
  _ziran_avif_meson_list(c_args "${flags}")
  set(machine "[binaries]\nc = ${c}\nar = '${CMAKE_AR}'\n")
  if(CMAKE_STRIP)
    string(APPEND machine "strip = '${CMAKE_STRIP}'\n")
  endif()
  string(APPEND machine "\n[built-in options]\nc_args = ${c_args}\n")
  if(CMAKE_CROSSCOMPILING)
    string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" processor)
    if(processor MATCHES "^(aarch64|arm64)")
      set(family aarch64)
    elseif(processor MATCHES "^arm")
      set(family arm)
    elseif(processor MATCHES "^(x86_64|amd64)$")
      set(family x86_64)
    elseif(processor MATCHES "^(i.86|x86)$")
      set(family x86)
    else()
      message(FATAL_ERROR "dav1d: unvalidated target processor ${CMAKE_SYSTEM_PROCESSOR}")
    endif()
    if(ANDROID)
      set(system android)
    else()
      string(TOLOWER "${CMAKE_SYSTEM_NAME}" system)
    endif()
    string(APPEND machine "\n[properties]\nneeds_exe_wrapper = true\n"
      "\n[host_machine]\nsystem = '${system}'\ncpu_family = '${family}'\ncpu = '${processor}'\nendian = 'little'\n")
    set(machine_option "--cross-file=${build}-machine.ini")
  else()
    set(machine_option "--native-file=${build}-machine.ini")
  endif()
  file(WRITE "${build}-machine.ini" "${machine}")
  if(NOT ZIRAN_AVIF_DAV1D_JOBS)
    set(ZIRAN_AVIF_DAV1D_JOBS 4)
  endif()
  # Configure always starts from an empty Meson tree; steps run in -step.
  ExternalProject_Add(ziran_avif_dav1d
    SOURCE_DIR "${source}"
    BINARY_DIR "${build}-step"
    INSTALL_DIR "${install}"
    STAMP_DIR "${build}-stamp"
    TMP_DIR "${build}-tmp"
    DOWNLOAD_COMMAND ""
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND "${CMAKE_COMMAND}" -E rm -rf "${build}"
      COMMAND ${meson} setup --buildtype=release --default-library=static
      --prefix=<INSTALL_DIR> --libdir=lib -Denable_asm=true -Denable_tools=false
      -Denable_tests=false -Denable_examples=false -Denable_docs=false
      "${machine_option}" "${build}" <SOURCE_DIR>
    BUILD_COMMAND ${meson} compile -C "${build}" -j ${ZIRAN_AVIF_DAV1D_JOBS}
    INSTALL_COMMAND ${meson} install -C "${build}" --no-rebuild
    BUILD_BYPRODUCTS "${install}/lib/libdav1d.a")
  add_library(dav1d::dav1d STATIC IMPORTED GLOBAL)
  set_target_properties(dav1d::dav1d PROPERTIES IMPORTED_LOCATION "${install}/lib/libdav1d.a" AVIF_LOCAL ON)
  target_include_directories(dav1d::dav1d INTERFACE "${install}/include")
  add_dependencies(dav1d::dav1d ziran_avif_dav1d)
endfunction()

# ziran_avif_add_native(AVIF_SOURCE path AOM_SOURCE path DAV1D_SOURCE path
#                       [BUILD_SHARED_BRIDGE]
#                       [SHARED_TARGET_NAME name] [SHARED_OUTPUT_NAME name])
# Public static target: ziran_avif::static. Optional shared target: avif_bridge.
# dav1d is the default decoder; libaom is the explicit comparison oracle.
function(ziran_avif_add_native)
  cmake_parse_arguments(codec "BUILD_SHARED_BRIDGE" "AVIF_SOURCE;AOM_SOURCE;DAV1D_SOURCE;SHARED_TARGET_NAME;SHARED_OUTPUT_NAME" "" ${ARGN})
  if(codec_UNPARSED_ARGUMENTS OR NOT codec_AVIF_SOURCE OR NOT codec_AOM_SOURCE OR NOT codec_DAV1D_SOURCE)
    message(FATAL_ERROR "ziran_avif_add_native requires AVIF_SOURCE, AOM_SOURCE and DAV1D_SOURCE")
  endif()
  if(NOT ANDROID AND NOT CMAKE_SYSTEM_NAME MATCHES "^(Linux|Windows|Darwin)$")
    message(FATAL_ERROR "ziran_avif native supports Linux/Android and existing Windows/Darwin static consumers")
  endif()
  if(codec_BUILD_SHARED_BRIDGE AND (ANDROID OR NOT CMAKE_SYSTEM_NAME STREQUAL "Linux"))
    message(FATAL_ERROR "ziran_avif shared bridge is validated only on Linux")
  endif()
  find_package(Git REQUIRED)
  _ziran_avif_source(libavif "${codec_AVIF_SOURCE}" 1aadfad932c98c069a1204261b1856f81f3bc199 include/avif/avif.h)
  _ziran_avif_source(libaom "${codec_AOM_SOURCE}" d772e334cc724105040382a977ebb10dfd393293 aom/aom_decoder.h)
  _ziran_avif_source(dav1d "${codec_DAV1D_SOURCE}" 54706fc6bc0cdecab7e9593974a4039cc038fca7 include/dav1d/dav1d.h)
  if(NOT codec_SHARED_TARGET_NAME)
    set(codec_SHARED_TARGET_NAME avif_bridge)
  endif()
  set(identity "${codec_AVIF_SOURCE}|${codec_AOM_SOURCE}|${codec_DAV1D_SOURCE}|${codec_BUILD_SHARED_BRIDGE}|${codec_SHARED_TARGET_NAME}|${codec_SHARED_OUTPUT_NAME}")
  if(TARGET ziran_avif::static)
    get_property(existing GLOBAL PROPERTY ZIRAN_AVIF_NATIVE_IDENTITY)
    if(NOT existing STREQUAL identity)
      message(FATAL_ERROR "ziran_avif native already configured with different sources/options")
    endif()
    return()
  endif()
  if(TARGET aom OR TARGET avif OR TARGET avif_static OR TARGET dav1d::dav1d)
    message(FATAL_ERROR "Use the package-owned AVIF recipe before defining codec targets")
  endif()
  set_property(GLOBAL PROPERTY ZIRAN_AVIF_NATIVE_IDENTITY "${identity}")
  set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
  set(CMAKE_POSITION_INDEPENDENT_CODE ON)
  # libaom is the single-threaded oracle; dav1d supplies decode threads.
  foreach(option ENABLE_DOCS ENABLE_EXAMPLES ENABLE_TESTDATA ENABLE_TESTS ENABLE_TOOLS CONFIG_AV1_ENCODER CONFIG_WEBM_IO CONFIG_LIBYUV CONFIG_MULTITHREAD)
    set(${option} 0 CACHE BOOL "" FORCE)
  endforeach()
  set(CONFIG_AV1_DECODER 1 CACHE BOOL "" FORCE)
  set(CONFIG_PIC 1 CACHE BOOL "" FORCE)
  if(ANDROID_ABI STREQUAL "arm64-v8a")
    set(AOM_TARGET_CPU arm64 CACHE STRING "" FORCE)
  elseif(ANDROID_ABI STREQUAL "armeabi-v7a")
    set(AOM_TARGET_CPU armv7 CACHE STRING "" FORCE)
    # The libaom oracle keeps alignment-safe portable CfL kernels for the pinned
    # AOM/NDK. The default dav1d engine keeps its ARMv7 NEON assembly.
    set(ENABLE_NEON OFF CACHE BOOL "ARMv7 libaom oracle kernels must accept unaligned buffers" FORCE)
  endif()
  add_subdirectory("${codec_AOM_SOURCE}" "${CMAKE_CURRENT_BINARY_DIR}/aom" EXCLUDE_FROM_ALL)
  target_include_directories(aom INTERFACE "$<BUILD_INTERFACE:${codec_AOM_SOURCE}>" "$<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/aom>")
  _ziran_avif_dav1d("${codec_DAV1D_SOURCE}")
  set(AVIF_CODEC_AOM SYSTEM CACHE STRING "" FORCE)
  set(AVIF_CODEC_AOM_ENCODE OFF CACHE BOOL "" FORCE)
  set(AVIF_CODEC_AOM_DECODE ON CACHE BOOL "" FORCE)
  set(AVIF_CODEC_DAV1D SYSTEM CACHE STRING "" FORCE)
  foreach(option LIBGAV1 RAV1E SVT AVM)
    set(AVIF_CODEC_${option} OFF CACHE STRING "" FORCE)
  endforeach()
  foreach(option LIBYUV LIBSHARPYUV JPEG ZLIBPNG)
    set(AVIF_${option} OFF CACHE STRING "" FORCE)
  endforeach()
  foreach(option APPS TESTS EXAMPLES)
    set(AVIF_BUILD_${option} OFF CACHE BOOL "" FORCE)
  endforeach()
  add_subdirectory("${codec_AVIF_SOURCE}" "${CMAKE_CURRENT_BINARY_DIR}/avif" EXCLUDE_FROM_ALL)
  # libavif's YUV->RGB conversion is floating point. Compilers that fuse
  # multiply-adds by default (GCC on AArch64, Clang on arm64) rounded the same
  # frame to different RGBA bytes there; unfused arithmetic keeps every target
  # bit-exact with the strict goldens.
  if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(avif_obj PRIVATE -ffp-contract=off)
  endif()
  # Upstream's merged avif_static archive (libavif plus dav1d) does not export
  # libaom or the thread/math link requirements. Give consumers one target.
  set(THREADS_PREFER_PTHREAD_FLAG ON)
  find_package(Threads REQUIRED)
  add_library(ziran_avif_static INTERFACE)
  target_link_libraries(ziran_avif_static INTERFACE avif_static aom Threads::Threads ${CMAKE_DL_LIBS})
  if(NOT WIN32)
    target_link_libraries(ziran_avif_static INTERFACE m)
  endif()
  add_library(ziran_avif::static ALIAS ziran_avif_static)
  if(codec_BUILD_SHARED_BRIDGE)
    target_compile_definitions(avif_obj PRIVATE AVIF_DLL AVIF_BUILDING_SHARED_LIBS)
    add_library(${codec_SHARED_TARGET_NAME} SHARED $<TARGET_OBJECTS:avif_obj>)
    target_link_libraries(${codec_SHARED_TARGET_NAME} PRIVATE aom dav1d::dav1d Threads::Threads ${CMAKE_DL_LIBS} m)
    target_link_options(${codec_SHARED_TARGET_NAME} PRIVATE "LINKER:--no-undefined")
    if(codec_SHARED_OUTPUT_NAME)
      set_target_properties(${codec_SHARED_TARGET_NAME} PROPERTIES OUTPUT_NAME "${codec_SHARED_OUTPUT_NAME}")
    endif()
  endif()
endfunction()
