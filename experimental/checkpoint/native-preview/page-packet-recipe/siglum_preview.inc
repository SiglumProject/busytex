/* Experimental exact page-content capture. This yields only at the next
 * top-level maincontrol loop boundary, after every shipout C frame returned.
 * It is forward continuation in the SAME live instance, not another snapshot.
 */
#include <stdlib.h>
#include <string.h>
#include "siglum_preview_layout.h"

#define SIGLUM_PREVIEW_CONTENT_MAX (2 * 1024 * 1024)
#define SIGLUM_PREVIEW_RESOURCES_MAX (64 * 1024)
#define SIGLUM_PREVIEW_FONTS_MAX 512
#define SIGLUM_PREVIEW_WATCHED_OBJECTS_MAX 4096

typedef struct {
    unsigned char *bytes;
    int length, capacity, start, active, pdfos, error;
} siglum_preview_bytes;

static siglum_preview_bytes siglum_preview_content;
static siglum_preview_bytes siglum_preview_resources;
static int siglum_preview_target = 0;
static int siglum_preview_ready = 0;
static int siglum_preview_yielded = 0;
int siglum_preview_is_paused = 0;
int siglum_preview_loop_done = 0;
static int siglum_preview_page_number = 0;
static int siglum_preview_width = 0;
static int siglum_preview_height = 0;
static int siglum_preview_flags = 0;
static int siglum_preview_font_count_value = 0;
static int siglum_preview_fonts[SIGLUM_PREVIEW_FONTS_MAX];
static int siglum_preview_object_count = 0;
static int siglum_preview_objects[SIGLUM_PREVIEW_WATCHED_OBJECTS_MAX];
static unsigned char siglum_preview_object_dirty[SIGLUM_PREVIEW_WATCHED_OBJECTS_MAX];
static int siglum_preview_resource_events_value = 0;

int siglum_preview_api_version(void) { return 1; }
int siglum_preview_resource_guard_api_version(void) { return 1; }

static void siglum_preview_release(siglum_preview_bytes *buffer)
{
    free(buffer->bytes);
    memset(buffer, 0, sizeof(*buffer));
}

int siglum_preview_arm(int page)
{
    if (siglum_preview_is_paused || siglum_finalize_is_paused || page <= totalpages || page > 1000000)
        return -1;
    siglum_preview_release(&siglum_preview_content);
    siglum_preview_release(&siglum_preview_resources);
    siglum_preview_target = page;
    siglum_preview_ready = 0;
    siglum_preview_yielded = 0;
    siglum_preview_loop_done = 0;
    siglum_preview_flags = 0;
    siglum_preview_font_count_value = 0;
    siglum_preview_page_number = 0;
    siglum_preview_object_count = 0;
    siglum_preview_resource_events_value = 0;
    return 0;
}

int siglum_preview_disarm(void)
{
    if (siglum_preview_is_paused || siglum_finalize_is_paused) return -1;
    siglum_preview_target = 0;
    siglum_preview_object_count = 0;
    siglum_preview_resource_events_value = 0;
    return 0;
}

/* Register only cached non-font closure objects that are already written in
 * the restored checkpoint. New/reserved objects need a full resource rebuild.
 * Registration must precede replay, not occur after seeing a desired result.
 */
int siglum_preview_guard_object(int object)
{
    int i;
    if (siglum_preview_target <= 0 || !siglum_checkpoint_is_paused ||
        object <= 0 || object > sysobjptr) return -1;
    if (objtab[object].int2 < 0) return -2;
    for (i = 0; i < siglum_preview_object_count; i++)
        if (siglum_preview_objects[i] == object) return 0;
    if (siglum_preview_object_count == SIGLUM_PREVIEW_WATCHED_OBJECTS_MAX) return -3;
    siglum_preview_objects[siglum_preview_object_count] = object;
    siglum_preview_object_dirty[siglum_preview_object_count++] = 0;
    return 0;
}

static void siglum_preview_before_object_write(int object)
{
    int i;
    if (siglum_preview_target <= 0 || siglum_preview_yielded) return;
    for (i = 0; i < siglum_preview_object_count; i++)
        if (siglum_preview_objects[i] == object) {
            siglum_preview_object_dirty[i] = 1;
            siglum_preview_resource_events_value |= 4;
        }
}

/* Invoked by linker wrappers around actual native setters, so hidden TeX
 * macros reach the same guard. Map changes=1, ToUnicode changes=2. */
void siglum_preview_resource_event(int event)
{
    if (siglum_preview_target > 0 && !siglum_preview_yielded)
        siglum_preview_resource_events_value |= event;
}

/* BEGIN literal grammar */
/* Native color stacks and drawing packages (pgf, and so TikZ and tcolorbox)
 * write through literal(). A literal is harmless to the page handoff when it
 * can only change the graphics state or draw paths: it then cannot show a
 * glyph, so TeX's used-character bitmaps stay complete, and the only named
 * resource it can use is a graphics state, which the host compares between
 * the old and the new page. Accepted, with exact operand counts:
 *   q Q cm w J j M i d  m l c v y h re  S s f F f* B B* b b* n W W*
 *   g G rg RG k K  and  /Name gs
 * Anything else fails closed: text and font operators, images, forms,
 * shadings, colour spaces, strings, dictionaries, comments. */
static int siglum_preview_is_drawing_literal_bytes(const unsigned char *at, const unsigned char *end)
{
    static const struct { const char *name; int numbers; } operators[] = {
        {"q", 0}, {"Q", 0}, {"cm", 6}, {"w", 1}, {"J", 1}, {"j", 1}, {"M", 1}, {"i", 1},
        {"m", 2}, {"l", 2}, {"c", 6}, {"v", 4}, {"y", 4}, {"h", 0}, {"re", 4},
        {"S", 0}, {"s", 0}, {"f", 0}, {"F", 0}, {"f*", 0}, {"B", 0}, {"B*", 0}, {"b", 0}, {"b*", 0},
        {"n", 0}, {"W", 0}, {"W*", 0},
        {"g", 1}, {"G", 1}, {"rg", 3}, {"RG", 3}, {"k", 4}, {"K", 4},
    };
    int numbers = 0, in_array = 0, array = 0, name = 0, digits, dots, length, i, known;
    const unsigned char *start;
    if (end < at || end - at > 65536) return 0;
    while (at < end) {
        while (at < end && *at <= 32) at++;
        if (at == end) break;
        if (*at == '[') {
            if (in_array || array || name || numbers) return 0;
            in_array = 1; at++;
            continue;
        }
        if (*at == ']') {
            if (!in_array) return 0;
            in_array = 0; array = 1; numbers = 0; at++;
            continue;
        }
        if (*at == '+' || *at == '-' || *at == '.' || (*at >= '0' && *at <= '9')) {
            digits = dots = 0;
            if (*at == '+' || *at == '-') at++;
            while (at < end && ((*at >= '0' && *at <= '9') || *at == '.')) {
                if (*at == '.') dots++; else digits++;
                at++;
            }
            if (!digits || dots > 1 || name || ++numbers > 32) return 0;
            if (at < end && *at > 32 && *at != ']' && !(in_array && *at == '[')) return 0;
            continue;
        }
        if (in_array) return 0;
        if (*at == '/') {
            if (name || array || numbers) return 0;
            start = ++at;
            while (at < end && *at > 32 && *at != '/' && *at != '[' && *at != ']' && *at != '(' && *at != ')' &&
                   *at != '<' && *at != '>' && *at != '{' && *at != '}' && *at != '%') at++;
            if (at == start || at - start > 127 || (at < end && *at > 32)) return 0;
            name = 1;
            continue;
        }
        start = at;
        while (at < end && *at > 32 && *at != '[' && *at != ']' && *at != '/') at++;
        length = (int)(at - start);
        if (at < end && *at > 32) return 0;
        if (name) {
            if (length != 2 || start[0] != 'g' || start[1] != 's') return 0;
        } else if (array) {
            /* A dash pattern: an array of numbers, then the phase. */
            if (length != 1 || start[0] != 'd' || numbers != 1) return 0;
        } else {
            known = 0;
            for (i = 0; i < (int)(sizeof(operators) / sizeof(operators[0])); i++)
                if ((int)strlen(operators[i].name) == length && !memcmp(operators[i].name, start, length)) {
                    if (operators[i].numbers != numbers) return 0;
                    known = 1;
                    break;
                }
            if (!known) return 0;
        }
        numbers = 0; array = 0; name = 0;
    }
    return !numbers && !in_array && !array && !name;
}
/* END literal grammar */

static int siglum_preview_is_drawing_literal(strnumber string)
{
    if (string < 0 || string >= strptr || strstart[string + 1] < strstart[string]) return 0;
    return siglum_preview_is_drawing_literal_bytes((const unsigned char *)&strpool[strstart[string]],
                                                    (const unsigned char *)&strpool[strstart[string + 1]]);
}

static void siglum_preview_literal_event(strnumber string)
{
    if (siglum_preview_target > 0 && !siglum_preview_yielded && !siglum_preview_is_drawing_literal(string))
        siglum_preview_resource_events_value |= 8;
}

int siglum_preview_resource_events(void)
{
    return siglum_preview_is_paused ? siglum_preview_resource_events_value : -1;
}

int siglum_preview_guard_object_status(int object)
{
    int i;
    if (!siglum_preview_is_paused) return -1;
    for (i = 0; i < siglum_preview_object_count; i++)
        if (siglum_preview_objects[i] == object) return siglum_preview_object_dirty[i];
    return -1;
}

int siglum_preview_font_global(int key)
{
    if (key == 1) return fixedgentounicode; /* Read-only latched debug value. */
    if (!siglum_preview_is_paused && !siglum_finalize_is_paused && !siglum_checkpoint_is_paused) return -1;
    /* fixedgentounicode is only latched inside closefilesandterminate, AFTER
     * our page/font handoffs. Compare the pending setting it will actually use.
     */
    if (key == 0) return zeqtb[SIGLUM_PREVIEW_EQTB_GENERATE_UNICODE].cint;
    return -1;
}

static int siglum_preview_should_capture(int shippingpage)
{
    return shippingpage && siglum_preview_target > 0 &&
        siglum_preview_target == totalpages + 1 && !siglum_preview_ready;
}

static void siglum_preview_append(siglum_preview_bytes *buffer, int limit)
{
    int count, capacity;
    unsigned char *bytes;
    if (!buffer->active || buffer->error) return;
    if (buffer->pdfos != (int)pdfosmode || buffer->start < 0 || buffer->start > pdfptr) {
        buffer->error = 1;
        return;
    }
    count = pdfptr - buffer->start;
    if (count > limit - buffer->length) {
        buffer->error = 2;
        return;
    }
    if (buffer->length + count > buffer->capacity) {
        capacity = buffer->capacity ? buffer->capacity : 4096;
        while (capacity < buffer->length + count && capacity < limit) capacity *= 2;
        if (capacity > limit) capacity = limit;
        bytes = (unsigned char *)realloc(buffer->bytes, (size_t)capacity);
        if (bytes == NULL) {
            buffer->error = 3;
            return;
        }
        buffer->bytes = bytes;
        buffer->capacity = capacity;
    }
    if (count > 0) memcpy(buffer->bytes + buffer->length, pdfbuf + buffer->start, (size_t)count);
    buffer->length += count;
    buffer->start = pdfptr;
}

static void siglum_preview_begin(siglum_preview_bytes *buffer)
{
    buffer->start = pdfptr;
    buffer->pdfos = pdfosmode;
    buffer->active = 1;
}

static void siglum_preview_end(siglum_preview_bytes *buffer, int limit)
{
    siglum_preview_append(buffer, limit);
    buffer->active = 0;
}

static void siglum_preview_before_flush(void)
{
    if (pdfosmode) return; /* pdfflush does not consume object-stream bytes. */
    siglum_preview_append(&siglum_preview_content, SIGLUM_PREVIEW_CONTENT_MAX);
    siglum_preview_append(&siglum_preview_resources, SIGLUM_PREVIEW_RESOURCES_MAX);
    if (siglum_preview_content.active) siglum_preview_content.start = 0;
    if (siglum_preview_resources.active) siglum_preview_resources.start = 0;
}

static void siglum_preview_page_metadata(void)
{
    memoryword *mem = zmem, *eqtb = zeqtb;
    int k, f, i, known;
    siglum_preview_page_number = totalpages;
    siglum_preview_width = curpagewidth;
    siglum_preview_height = curpageheight;
    /* Unknown/non-font resources and page attributes require a full fallback.
     * The caller must also validate the copied resource body and font closure.
     */
    if (pdfximagelist != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 1;
    if (pdfxformlist != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 2;
    if (pdfobjlist != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 4;
    if (pdfannotlist != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 8;
    if (pdflinklist != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 16;
    if (eqtb[SIGLUM_PREVIEW_EQTB_PAGE_ATTR].hh.v.RH != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 32;
    if (eqtb[SIGLUM_PREVIEW_EQTB_PAGE_RESOURCES].hh.v.RH != SIGLUM_PREVIEW_NIL) siglum_preview_flags |= 64;
    if (pdfpagegroupval != 0) siglum_preview_flags |= 128;
    for (k = pdffontlist; k != SIGLUM_PREVIEW_NIL; k = mem[k].hh.v.RH) {
        f = mem[k].hh.v.LH;
        if (pdffontnum[f] < 0) f = -(int)pdffontnum[f];
        known = 0;
        for (i = 0; i < siglum_preview_font_count_value; i++)
            if (siglum_preview_fonts[i] == f) known = 1;
        if (known) continue;
        if (siglum_preview_font_count_value == SIGLUM_PREVIEW_FONTS_MAX) {
            siglum_preview_flags |= 256;
            break;
        }
        siglum_preview_fonts[siglum_preview_font_count_value++] = f;
    }
}

static void siglum_preview_shipout_done(void)
{
    if (siglum_preview_content.active || siglum_preview_resources.active ||
        !siglum_preview_content.bytes || !siglum_preview_resources.bytes)
        siglum_preview_flags |= 512;
    if (siglum_preview_content.error || siglum_preview_resources.error)
        siglum_preview_flags |= 1024;
    if (history != 0 && history != 1) siglum_preview_flags |= 2048;
    siglum_preview_ready = 1;
}

int siglum_preview_poll(void)
{
    if (!siglum_preview_ready || siglum_preview_yielded) return 0;
    siglum_preview_is_paused = 1;
    return 1;
}

int siglum_preview_after_maincontrol(void)
{
    if (siglum_preview_is_paused) return 1;
    if (!siglum_preview_ready || siglum_preview_yielded) return 0;
    /* maincontrol reached its genuine end before another loop poll. */
    siglum_preview_loop_done = 1;
    siglum_preview_is_paused = 1;
    return 1;
}

int siglum_preview_enter_continue(void)
{
    if (!siglum_preview_is_paused) return -1;
    siglum_preview_is_paused = 0;
    siglum_preview_yielded = 1;
    siglum_preview_target = 0;
    return siglum_preview_loop_done;
}

/* Reuse the same bounded buffers only after the host copied/discarded the old
 * packet. Guard events and watched objects remain cumulative from the original
 * checkpoint. No source refresh, new snapshot or heap allocation is required.
 */
int siglum_preview_enter_next(int page)
{
    int done;
    if (!siglum_preview_is_paused || page <= totalpages || page > 1000000) return -1;
    done = siglum_preview_loop_done;
    siglum_preview_is_paused = 0;
    siglum_preview_target = done ? 0 : page;
    siglum_preview_ready = 0;
    siglum_preview_yielded = 0;
    siglum_preview_loop_done = 0;
    siglum_preview_flags = 0;
    siglum_preview_font_count_value = 0;
    siglum_preview_page_number = 0;
    siglum_preview_content.length = siglum_preview_content.start = siglum_preview_content.active = siglum_preview_content.error = 0;
    siglum_preview_resources.length = siglum_preview_resources.start = siglum_preview_resources.active = siglum_preview_resources.error = 0;
    return done;
}

int siglum_preview_paused(void) { return siglum_preview_is_paused; }
int siglum_preview_page(void) { return siglum_preview_is_paused ? siglum_preview_page_number : 0; }
int siglum_preview_width_sp(void) { return siglum_preview_is_paused ? siglum_preview_width : 0; }
int siglum_preview_height_sp(void) { return siglum_preview_is_paused ? siglum_preview_height : 0; }
int siglum_preview_guard_flags(void) { return siglum_preview_is_paused ? siglum_preview_flags : -1; }
int siglum_preview_content_length(void) { return siglum_preview_is_paused ? siglum_preview_content.length : 0; }
const unsigned char *siglum_preview_content_data(void) { return siglum_preview_is_paused ? siglum_preview_content.bytes : NULL; }
int siglum_preview_resources_length(void) { return siglum_preview_is_paused ? siglum_preview_resources.length : 0; }
const unsigned char *siglum_preview_resources_data(void) { return siglum_preview_is_paused ? siglum_preview_resources.bytes : NULL; }
int siglum_preview_font_count(void) { return siglum_preview_is_paused ? siglum_preview_font_count_value : 0; }
int siglum_preview_font_index(int index)
{
    return siglum_preview_is_paused && index >= 0 && index < siglum_preview_font_count_value
        ? siglum_preview_fonts[index] : -1;
}

/* Metadata is valid only while a preview or post-layout handoff is paused.
 * The host copies it before continuation; libpdffinish frees map entries.
 * Character bits are per-TeX-font. The host ORs aliases sharing base index.
 */
static int siglum_preview_font_valid(int f)
{
    return (siglum_preview_is_paused || siglum_finalize_is_paused) && f > 0 && f <= fontptr && fontused[f];
}
int siglum_preview_font_max_index(void)
{
    return (siglum_preview_is_paused || siglum_finalize_is_paused) ? fontptr : 0;
}
int siglum_preview_font_info(int f, int key)
{
    fm_entry *fm;
    if (!siglum_preview_font_valid(f)) return -1;
    fm = hasfmentry(f) ? (fm_entry *)pdffontmap[f] : NULL;
    switch (key) {
    case 0: return pdffontnum[f] < 0 ? -(int)pdffontnum[f] : f;
    case 1: return pdffontnum[f];
    case 2: return fontsize[f];
    case 3: return fontdsize[f];
    case 4: return pdffontsize[f];
    case 5: return fm ? fm->type : -1;
    case 6: return fm ? fm->slant : 0;
    case 7: return fm ? fm->extend : 0;
    case 8: return fm ? fm->pid : 0;
    case 9: return fm ? fm->eid : 0;
    case 10: return pdffontnobuiltintounicode[f];
    case 11: return fontbc[f];
    case 12: return fontec[f];
    case 13: return (int)(((unsigned int)fontcheck[f].b0 << 24) | ((unsigned int)fontcheck[f].b1 << 16) |
                         ((unsigned int)fontcheck[f].b2 << 8) | (unsigned int)fontcheck[f].b3);
    case 14: return fm ? fm->fd_flags : 0;
    default: return -1;
    }
}
const char *siglum_preview_font_string(int f, int key)
{
    fm_entry *fm;
    if (!siglum_preview_font_valid(f) || !hasfmentry(f)) return NULL;
    fm = (fm_entry *)pdffontmap[f];
    switch (key) {
    case 0: return fm->tfm_name;
    case 1: return fm->ff_name;
    case 2: return fm->encname;
    case 3: return fm->ps_name;
    case 4: return fm->sfd_name;
    default: return NULL;
    }
}
const unsigned char *siglum_preview_font_bits(int f)
{
    return siglum_preview_font_valid(f) ? pdfcharused[f] : NULL;
}
int siglum_preview_font_attr_length(int f)
{
    int s;
    if (!siglum_preview_font_valid(f)) return 0;
    s = pdffontattr[f];
    return s > 0 && s < strptr ? strstart[s + 1] - strstart[s] : 0;
}
const unsigned char *siglum_preview_font_attr_data(int f)
{
    return siglum_preview_font_attr_length(f) ? strpool + strstart[pdffontattr[f]] : NULL;
}
