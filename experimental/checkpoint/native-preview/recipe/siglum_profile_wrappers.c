#include <stddef.h>
#include <stdio.h>
#include "siglum_profile.h"

extern int __real_deflate(void *stream, int flush);
int __wrap_deflate(void *stream, int flush)
{
    int result;
    double started;
    if (!siglum_profile_enabled)
        return __real_deflate(stream, flush);
    started = siglum_profile_begin(SIGLUM_PHASE_DEFLATE);
    result = __real_deflate(stream, flush);
    siglum_profile_end(SIGLUM_PHASE_DEFLATE, started);
    return result;
}

extern size_t __real_fwrite(const void *ptr, size_t size, size_t count, FILE *stream);
size_t __wrap_fwrite(const void *ptr, size_t size, size_t count, FILE *stream)
{
    size_t result;
    double started;
    if (!siglum_profile_enabled)
        return __real_fwrite(ptr, size, count, stream);
    started = siglum_profile_begin(SIGLUM_PHASE_FWRITE);
    result = __real_fwrite(ptr, size, count, stream);
    siglum_profile_end(SIGLUM_PHASE_FWRITE, started);
    siglum_profile_add_bytes(SIGLUM_PHASE_FWRITE, (double)result * (double)size);
    return result;
}
