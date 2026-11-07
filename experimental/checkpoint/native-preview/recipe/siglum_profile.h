#ifndef SIGLUM_PROFILE_H
#define SIGLUM_PROFILE_H

enum siglum_phase {
    SIGLUM_PHASE_RESUME_TOTAL = 0,
    SIGLUM_PHASE_MAINCONTROL,
    SIGLUM_PHASE_FINALCLEANUP,
    SIGLUM_PHASE_CLOSEFILES,
    SIGLUM_PHASE_FONT_DICTIONARIES,
    SIGLUM_PHASE_FONT_STREAMS,
    SIGLUM_PHASE_SHIPOUT,
    SIGLUM_PHASE_PAGE_LISTS,
    SIGLUM_PHASE_DEFLATE,
    SIGLUM_PHASE_FWRITE,
    SIGLUM_PHASE_FORMAT_LOAD,
    SIGLUM_PHASE_PDF_FLUSH,
    SIGLUM_PHASE_COUNT
};

extern int siglum_profile_enabled;
double siglum_profile_begin(int phase);
void siglum_profile_end(int phase, double started);
void siglum_profile_add_bytes(int phase, double bytes);
void siglum_profile_reset(void);
void siglum_profile_enable(int enabled);
double siglum_profile_get_time(int phase);
double siglum_profile_get_bytes(int phase);
int siglum_profile_get_count(int phase);
int siglum_profile_phase_count(void);

#define SIGLUM_PROFILE_CALL(phase, expression) do { \
    double siglum_profile_started = siglum_profile_begin(phase); \
    expression; \
    siglum_profile_end(phase, siglum_profile_started); \
} while (0)

#endif
