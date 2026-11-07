#include <emscripten/emscripten.h>
#include <string.h>

int siglum_profile_enabled = 0;
static double siglum_profile_times[SIGLUM_PHASE_COUNT];
static double siglum_profile_bytes[SIGLUM_PHASE_COUNT];
static unsigned int siglum_profile_counts[SIGLUM_PHASE_COUNT];

void siglum_profile_reset(void)
{
    memset(siglum_profile_times, 0, sizeof(siglum_profile_times));
    memset(siglum_profile_bytes, 0, sizeof(siglum_profile_bytes));
    memset(siglum_profile_counts, 0, sizeof(siglum_profile_counts));
}

void siglum_profile_enable(int enabled)
{
    siglum_profile_enabled = enabled != 0;
    siglum_profile_reset();
}

double siglum_profile_begin(int phase)
{
    (void)phase;
    return siglum_profile_enabled ? emscripten_get_now() : 0.0;
}

void siglum_profile_end(int phase, double started)
{
    if (!siglum_profile_enabled || phase < 0 || phase >= SIGLUM_PHASE_COUNT)
        return;
    siglum_profile_times[phase] += emscripten_get_now() - started;
    siglum_profile_counts[phase]++;
}

void siglum_profile_add_bytes(int phase, double bytes)
{
    if (siglum_profile_enabled && phase >= 0 && phase < SIGLUM_PHASE_COUNT)
        siglum_profile_bytes[phase] += bytes;
}

double siglum_profile_get_time(int phase)
{
    return phase >= 0 && phase < SIGLUM_PHASE_COUNT ? siglum_profile_times[phase] : -1.0;
}

double siglum_profile_get_bytes(int phase)
{
    return phase >= 0 && phase < SIGLUM_PHASE_COUNT ? siglum_profile_bytes[phase] : -1.0;
}

int siglum_profile_get_count(int phase)
{
    return phase >= 0 && phase < SIGLUM_PHASE_COUNT ? (int)siglum_profile_counts[phase] : -1;
}

int siglum_profile_phase_count(void)
{
    return SIGLUM_PHASE_COUNT;
}
