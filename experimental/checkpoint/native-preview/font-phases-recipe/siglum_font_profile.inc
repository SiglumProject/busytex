#include <emscripten/emscripten.h>
#include <string.h>
extern int siglum_profile_enabled;
static double siglum_font_times[SIGLUM_FONT_PHASE_COUNT];
static unsigned int siglum_font_counts[SIGLUM_FONT_PHASE_COUNT];
void siglum_font_profile_reset(void)
{
    memset(siglum_font_times, 0, sizeof(siglum_font_times));
    memset(siglum_font_counts, 0, sizeof(siglum_font_counts));
}
double siglum_font_profile_begin(void)
{
    return siglum_profile_enabled ? emscripten_get_now() : 0.0;
}
void siglum_font_profile_end(int phase, double started)
{
    if (!siglum_profile_enabled || phase < 0 || phase >= SIGLUM_FONT_PHASE_COUNT) return;
    siglum_font_times[phase] += emscripten_get_now() - started;
    siglum_font_counts[phase]++;
}
int siglum_font_profile_phase_count(void) { return SIGLUM_FONT_PHASE_COUNT; }
double siglum_font_profile_get_time(int phase)
{
    return phase >= 0 && phase < SIGLUM_FONT_PHASE_COUNT ? siglum_font_times[phase] : -1.0;
}
int siglum_font_profile_get_count(int phase)
{
    return phase >= 0 && phase < SIGLUM_FONT_PHASE_COUNT ? (int)siglum_font_counts[phase] : -1;
}
