#ifndef SIGLUM_FONT_PROFILE_H
#define SIGLUM_FONT_PROFILE_H
enum siglum_font_phase {
    SIGLUM_FONT_OPEN = 0, SIGLUM_FONT_ASCII, SIGLUM_FONT_EEXEC_START,
    SIGLUM_FONT_SUBRS, SIGLUM_FONT_CHARSTRINGS, SIGLUM_FONT_SUBSET_END,
    SIGLUM_FONT_CLOSE, SIGLUM_FONT_FULL_INCLUDE, SIGLUM_FONT_MAP_READ,
    SIGLUM_FONT_PHASE_COUNT
};
void siglum_font_profile_reset(void);
double siglum_font_profile_begin(void);
void siglum_font_profile_end(int phase, double started);
int siglum_font_profile_phase_count(void);
double siglum_font_profile_get_time(int phase);
int siglum_font_profile_get_count(int phase);
#define SIGLUM_FONT_PROFILE_CALL(phase, expression) do { \
    double siglum_font_started = siglum_font_profile_begin(); \
    expression; \
    siglum_font_profile_end(phase, siglum_font_started); \
} while (0)
#endif
