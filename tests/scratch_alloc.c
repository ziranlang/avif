/* Test-only linker allocator probe: record requested bytes, not malloc RSS. */
#include <stddef.h>
void *__real_realloc(void *, size_t);
void *__real_malloc(size_t);
void *__real_calloc(size_t, size_t);
static size_t largest;
void avif_test_reset_allocations(void) { largest = 0; }
size_t avif_test_largest_allocation(void) { return largest; }
void *__wrap_realloc(void *pointer, size_t bytes) {
    if (bytes > largest) largest = bytes;
    return __real_realloc(pointer, bytes);
}
void *__wrap_malloc(size_t bytes) {
    if (bytes > largest) largest = bytes;
    return __real_malloc(bytes);
}
void *__wrap_calloc(size_t count, size_t bytes) {
    if (count * bytes > largest) largest = count * bytes;
    return __real_calloc(count, bytes);
}
