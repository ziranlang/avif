include("${CMAKE_CURRENT_LIST_DIR}/ZiranAvif.cmake")

if(DEFINED ZIRAN_SOURCE_libaom)
    set(avif_mode AOM_SOURCE "${ZIRAN_SOURCE_libaom}")
else()
    set(avif_mode DECODE_ONLY)
endif()
ziran_avif_add_native(AVIF_SOURCE "${ZIRAN_SOURCE_libavif}"
    DAV1D_SOURCE "${ZIRAN_SOURCE_dav1d}" ${avif_mode})
target_link_libraries("${ZIRAN_ANDROID_TARGET}" PRIVATE ziran_avif::static)
