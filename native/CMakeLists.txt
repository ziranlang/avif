cmake_minimum_required(VERSION 3.17)
project(ziran_avif C CXX ASM)
include("${CMAKE_CURRENT_LIST_DIR}/ZiranAvif.cmake")
ziran_avif_add_native(AVIF_SOURCE "${AVIF_SOURCE}" AOM_SOURCE "${AOM_SOURCE}" DAV1D_SOURCE "${DAV1D_SOURCE}" BUILD_SHARED_BRIDGE)
