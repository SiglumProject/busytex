/* Experimental, instance-local cooperative pdfTeX checkpoints.
 * Included after pdftexd.h in the generated pdftex0.c. No engine state is
 * serialized by this layer: the host must snapshot this exact instance's
 * linear memory AND its mutable JS filesystem after prepare_snapshot().
 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int siglum_checkpoint_is_paused = 0;
int siglum_checkpoint_resume_enter = 0;
static int siglum_checkpoint_target_line = 0;
static char siglum_checkpoint_target_file[4096];
static char siglum_checkpoint_active_file[4096];
static char siglum_checkpoint_raw_file[4096];
static char siglum_checkpoint_joined_file[8192];
static long siglum_checkpoint_input_positions[128];
static unsigned char siglum_checkpoint_input_active[128];
static long siglum_checkpoint_read_positions[16];
static unsigned char siglum_checkpoint_read_active[16];

static const char *siglum_checkpoint_filename_internal(void)
{
    strnumber name;
    int i, size, start, count, output;
    if (inopen <= 0 || curinput.statefield == 0 || curinput.namefield <= 19) {
        siglum_checkpoint_active_file[0] = 0;
        siglum_checkpoint_raw_file[0] = 0;
        return siglum_checkpoint_active_file;
    }
    name = fullsourcefilenamestack[curinput.indexfield];
    if (name <= 0 || name >= strptr) return "";
    size = strstart[name + 1] - strstart[name];
    if (size < 0 || size >= (int)sizeof(siglum_checkpoint_active_file))
        return "";
    /* The process cwd is fixed throughout this experimental no-shell-escape
     * invocation. Normalize only when the raw physical filename changes;
     * maincontrol's frequent boundary checks make no per-token FS calls. */
    if (strlen(siglum_checkpoint_raw_file) == (size_t)size
        && !memcmp(siglum_checkpoint_raw_file, strpool + strstart[name], size))
        return siglum_checkpoint_active_file;
    siglum_checkpoint_active_file[0] = 0;
    for (i = 0; i < size; ++i)
        siglum_checkpoint_raw_file[i] = (char)strpool[strstart[name] + i];
    siglum_checkpoint_raw_file[size] = 0;
    if (siglum_checkpoint_raw_file[0] == '/') {
        strcpy(siglum_checkpoint_joined_file, siglum_checkpoint_raw_file);
    } else {
        if (!getcwd(siglum_checkpoint_joined_file, sizeof(siglum_checkpoint_joined_file))) return "";
        count = (int)strlen(siglum_checkpoint_joined_file);
        if (count + size + 2 > (int)sizeof(siglum_checkpoint_joined_file)) return "";
        siglum_checkpoint_joined_file[count++] = '/';
        memcpy(siglum_checkpoint_joined_file + count, siglum_checkpoint_raw_file, size + 1);
    }
    output = 1;
    siglum_checkpoint_active_file[0] = '/';
    i = 0;
    while (siglum_checkpoint_joined_file[i]) {
        while (siglum_checkpoint_joined_file[i] == '/') ++i;
        start = i;
        while (siglum_checkpoint_joined_file[i] && siglum_checkpoint_joined_file[i] != '/') ++i;
        count = i - start;
        if (!count || (count == 1 && siglum_checkpoint_joined_file[start] == '.')) continue;
        if (count == 2 && siglum_checkpoint_joined_file[start] == '.'
            && siglum_checkpoint_joined_file[start + 1] == '.') {
            while (output > 1 && siglum_checkpoint_active_file[output - 1] != '/') --output;
            if (output > 1) --output;
            continue;
        }
        if (output + count + 2 >= (int)sizeof(siglum_checkpoint_active_file)) return "";
        if (output > 1) siglum_checkpoint_active_file[output++] = '/';
        memcpy(siglum_checkpoint_active_file + output, siglum_checkpoint_joined_file + start, count);
        output += count;
    }
    siglum_checkpoint_active_file[output] = 0;
    return siglum_checkpoint_active_file;
}

int siglum_checkpoint_arm(const char *filename, int next_line)
{
    if (!filename || strlen(filename) >= sizeof(siglum_checkpoint_target_file)
        || next_line < 1) return -1;
    strcpy(siglum_checkpoint_target_file, filename);
    siglum_checkpoint_target_line = next_line;
    return 0;
}

void siglum_checkpoint_disarm(void)
{
    siglum_checkpoint_target_line = 0;
}

/* Called only at maincontrol's lab60, before getxtoken. There are no
 * live automatic variables at this label. Requiring an exhausted physical
 * input line avoids invalidating unread TeX buffer text when the host edits
 * later source lines. Token-list input, pseudofiles and scanners do not pause.
 */
static int siglum_checkpoint_poll(void)
{
    if (!siglum_checkpoint_target_line || curinput.statefield == 0
        || curinput.namefield <= 19 || curinput.locfield <= curinput.limitfield
        || scannerstatus != 0 || forceeof || inopen <= 0
        || line + 1 < siglum_checkpoint_target_line) return 0;
    if (strcmp(siglum_checkpoint_filename_internal(), siglum_checkpoint_target_file))
        return 0;
    siglum_checkpoint_target_line = 0;
    siglum_checkpoint_is_paused = 1;
    return 1;
}

int siglum_checkpoint_paused(void) { return siglum_checkpoint_is_paused; }
int siglum_checkpoint_line(void) { return line; }
int siglum_checkpoint_next_line(void) { return line + 1; }
int siglum_checkpoint_total_pages(void) { return totalpages; }
int siglum_checkpoint_input_ptr(void) { return inputptr; }
int siglum_checkpoint_input_index(void) { return curinput.indexfield; }
int siglum_checkpoint_input_state(void) { return curinput.statefield; }
int siglum_checkpoint_buffer_loc(void) { return curinput.locfield; }
int siglum_checkpoint_buffer_limit(void) { return curinput.limitfield; }
int siglum_checkpoint_buffer_start(void) { return curinput.startfield; }
void *siglum_checkpoint_buffer(void) { return buffer; }
void *siglum_checkpoint_input_stack(void) { return inputstack; }
const char *siglum_checkpoint_filename(void) { return siglum_checkpoint_filename_internal(); }
int siglum_checkpoint_input_fd(void)
{
    if (!siglum_checkpoint_is_paused) return -1;
    return fileno(inputfile[curinput.indexfield]);
}
int siglum_checkpoint_input_offset(void)
{
    if (!siglum_checkpoint_is_paused) return -1;
    return (int)ftell(inputfile[curinput.indexfield]);
}

/* Flush all output before the host copies mutable MEMFS bytes. Record
 * logical C offsets, then discard libc read-ahead using fseek. Both the
 * resulting FILE structs and the JS stream positions belong in the snapshot.
 * Clear the same input buffers again after restoring memory and JS FS state.
 */
int siglum_checkpoint_prepare_snapshot(void)
{
    int i;
    if (!siglum_checkpoint_is_paused) return -1;
    if (fflush(NULL)) return -2;
    memset(siglum_checkpoint_input_active, 0, sizeof(siglum_checkpoint_input_active));
    memset(siglum_checkpoint_read_active, 0, sizeof(siglum_checkpoint_read_active));
    for (i = 1; i <= inopen && i < 128; ++i) {
        FILE *f;
        /* Pseudofiles have no physical source filename or FILE. */
        if (!fullsourcefilenamestack[i]) continue;
        f = inputfile[i];
        if (!f) return -3;
        siglum_checkpoint_input_positions[i] = ftell(f);
        if (siglum_checkpoint_input_positions[i] < 0
            || fseek(f, siglum_checkpoint_input_positions[i], SEEK_SET)) return -4;
        siglum_checkpoint_input_active[i] = 1;
    }
    for (i = 0; i < 16; ++i) {
        FILE *f;
        if (readopen[i] == 2) continue;
        f = readfile[i];
        if (!f) return -5;
        siglum_checkpoint_read_positions[i] = ftell(f);
        if (siglum_checkpoint_read_positions[i] < 0
            || fseek(f, siglum_checkpoint_read_positions[i], SEEK_SET)) return -6;
        siglum_checkpoint_read_active[i] = 1;
    }
    return 0;
}

int siglum_checkpoint_refresh_inputs(void)
{
    int i;
    if (!siglum_checkpoint_is_paused) return -1;
    for (i = 1; i < 128; ++i)
        if (siglum_checkpoint_input_active[i]
            && fseek(inputfile[i], siglum_checkpoint_input_positions[i], SEEK_SET))
            return -2;
    for (i = 0; i < 16; ++i)
        if (siglum_checkpoint_read_active[i]
            && fseek(readfile[i], siglum_checkpoint_read_positions[i], SEEK_SET))
            return -3;
    return 0;
}
