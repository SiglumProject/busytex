/* Included in generated pdftex0.c after pdftexd.h. The caller keeps this same
 * live instance intact during the handoff; no second engine or snapshot.
 *
 * Request collection deliberately does not open files or call kpse_find_file:
 * a failed lookup must not enter a font-library negative cache before the host
 * has fetched the files. hasfmentry only resolves the already loaded map.
 */
#include <string.h>

#define SIGLUM_FINALIZE_MAX_REQUESTS 2048

static int siglum_finalize_enabled = 0;
int siglum_finalize_is_paused = 0;
static int siglum_finalize_count = 0;
static int siglum_finalize_overflow = 0;
static int siglum_finalize_unsupported = 0;
static const char *siglum_finalize_names[SIGLUM_FINALIZE_MAX_REQUESTS];
static unsigned char siglum_finalize_kinds[SIGLUM_FINALIZE_MAX_REQUESTS];

int siglum_finalize_api_version(void) { return 1; }

int siglum_finalize_enable(int enabled)
{
    if (siglum_finalize_is_paused) return -1;
    siglum_finalize_enabled = enabled != 0;
    siglum_finalize_count = 0;
    siglum_finalize_overflow = 0;
    siglum_finalize_unsupported = 0;
    return 0;
}

int siglum_finalize_paused(void) { return siglum_finalize_is_paused; }
int siglum_finalize_request_count(void)
{
    return siglum_finalize_is_paused ? siglum_finalize_count : 0;
}
const char *siglum_finalize_request_name(int index)
{
    if (!siglum_finalize_is_paused || index < 0 || index >= siglum_finalize_count)
        return NULL;
    return siglum_finalize_names[index];
}
int siglum_finalize_request_kind(int index)
{
    if (!siglum_finalize_is_paused || index < 0 || index >= siglum_finalize_count)
        return 0;
    return siglum_finalize_kinds[index];
}
int siglum_finalize_request_overflow(void)
{
    return siglum_finalize_is_paused ? siglum_finalize_overflow : 0;
}
int siglum_finalize_unsupported_count(void)
{
    return siglum_finalize_is_paused ? siglum_finalize_unsupported : 0;
}

static void siglum_finalize_add(const char *name, int kind)
{
    int i;
    if (name == NULL || name[0] == 0) return;
    for (i = 0; i < siglum_finalize_count; i++)
        if (siglum_finalize_kinds[i] == kind &&
            strcmp(siglum_finalize_names[i], name) == 0)
            return;
    if (siglum_finalize_count == SIGLUM_FINALIZE_MAX_REQUESTS) {
        siglum_finalize_overflow = 1;
        return;
    }
    siglum_finalize_names[siglum_finalize_count] = name;
    siglum_finalize_kinds[siglum_finalize_count++] = kind;
}

int siglum_finalize_prepare(void)
{
    int f;
    fm_entry *fm;
    if (!siglum_finalize_enabled || siglum_finalize_is_paused ||
        fixedpdfoutput <= 0 || fixedpdfdraftmode != 0 || totalpages <= 0 ||
        (history != 0 && history != 1))
        return 0;
    siglum_finalize_count = 0;
    siglum_finalize_overflow = 0;
    siglum_finalize_unsupported = 0;
    for (f = 1; f <= fontptr; f++) {
        if (!fontused[f]) continue;
        if (!hasfmentry(f)) {
            siglum_finalize_unsupported++;
            continue;
        }
        fm = (fm_entry *)pdffontmap[f];
        if (is_pk(fm)) {
            siglum_finalize_unsupported++;
            continue;
        }
        /* Encodings can be needed even by an unembedded standard font. */
        siglum_finalize_add(fm->encname, 2);
        if (is_included(fm)) siglum_finalize_add(fm->ff_name, 1);
    }
    siglum_finalize_is_paused = 1;
    return 1;
}
