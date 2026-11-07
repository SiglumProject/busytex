from pathlib import Path
import json,shutil,hashlib,difflib,argparse
r=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description='Prepare same-stack runtime I/O against an existing checkpoint build')
parser.add_argument('--work',type=Path,default=r.parents[3])
parser.add_argument('--base-runtime',type=Path,required=True)
parser.add_argument('--base-commands',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();native=args.work.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
for p in args.base_runtime.iterdir():
 if p.suffix in ['.c','.h','.inc','.o']:shutil.copy2(p,out/p.name)
s=(native/'source/texlive/texk/kpathsea/tex-file.c').read_text()
original=s
bridge='''
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#include <kpathsea/db.h>
#include <kpathsea/readable.h>
EM_JS(int, siglum_resolve_input, (const char *name, int format, int must_exist, char *resolved, int capacity), {
  var callback = Module["siglumResolveInput"];
  return typeof callback === "function" ? callback(UTF8ToString(name), format, must_exist, resolved, capacity) : 0;
});
static kpathsea siglum_io_active_kpse = NULL;
static int siglum_io_active_format = -1;
int siglum_io_automatic_maps_allowed(void) { return siglum_io_active_format != kpse_fontmap_format; }
int siglum_io_api_version(void) { return 1; }
int siglum_io_register_file(const char *path) {
  if (!siglum_io_active_kpse || !path || path[0] != '/') return -1;
  kpathsea_db_insert(siglum_io_active_kpse, path);
  return 0;
}
#endif
'''
s=s.replace('#include <kpathsea/c-ctype.h>', '#include <kpathsea/c-ctype.h>\n'+bridge,1)
needle='''  /* Free the list we created. */'''
assert s.count(needle)==1
hook='''#ifdef __EMSCRIPTEN__
  /* Preserve the active TeX stack while the host resolves an exact missing
     runtime file. Ordinary search and project-file precedence happen first.
     An absent or unavailable provider leaves upstream behaviour unchanged. */
  if (! *ret) {
    for (count = 0; target[count]; count++) {
      char resolved[4096];
      resolved[0] = 0;
      kpathsea previous_kpse = siglum_io_active_kpse;
      int previous_format = siglum_io_active_format;
      siglum_io_active_format = format;
      siglum_io_active_kpse = kpse;
      int available = siglum_resolve_input(target[count], format, must_exist, resolved, sizeof(resolved));
      siglum_io_active_kpse = previous_kpse;
      siglum_io_active_format = previous_format;
      if (available > 0) {
        free(ret);
        /* The host registered exact mounted paths. Let Kpathsea retain its
           normal format-specific search ordering and duplicate-file policy. */
        ret = kpathsea_path_search_list_generic(kpse, FMT_INFO.path, target, true, all);
        if (*ret) break;
      }
    }
  }
#endif

'''
s=s.replace(needle,hook+needle,1)
(out/'tex-file.c').write_text(s)
patch=''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='a/source/texlive/texk/kpathsea/tex-file.c',tofile='b/source/texlive/texk/kpathsea/tex-file.c'))
(out/'kpathsea-live-input.patch').write_text(patch)
source=native/'source/texlive/texk/web2c/pdftexdir/mapfile.c'
m=source.read_text();original_map=m
queue='''
/* Demand-loaded package maps enter the normal font-map reader at its next
   lookup. Registering a path must not reenter TeX file I/O from Kpathsea. */
typedef struct siglum_io_map_node {
    char *command;
    struct siglum_io_map_node *next;
} siglum_io_map_node;
static siglum_io_map_node *siglum_io_maps_head = NULL;
static siglum_io_map_node *siglum_io_maps_tail = NULL;
static int siglum_io_maps_count = 0;
static int siglum_io_maps_reading = 0;
static void siglum_io_read_pending_maps(void);
extern int siglum_io_automatic_maps_allowed(void);
int siglum_io_queue_map(const char *path) {
    siglum_io_map_node *node;
    size_t length;
    /* An explicit map request owns its +/-/= semantics. Do not queue package
       maps behind that directive and accidentally undo a removal later. */
    if (!siglum_io_automatic_maps_allowed()) return 1;
    if (!path || path[0] != '/' || siglum_io_maps_count >= 128) return 0;
    length = strlen(path);
    if (length == 0 || length >= 4096 || strchr(path, ' ')) return 0;
    node = xmalloc(sizeof(*node));
    node->command = xmalloc(length + 2);
    node->command[0] = '+';
    memcpy(node->command + 1, path, length + 1);
    node->next = NULL;
    if (siglum_io_maps_tail) siglum_io_maps_tail->next = node;
    else siglum_io_maps_head = node;
    siglum_io_maps_tail = node;
    siglum_io_maps_count++;
    return 1;
}
'''
m=m.replace('static FILE *fm_file;', 'static FILE *fm_file;\n'+queue,1)
needle='''        fm_read_info();         /* only to read default map file */'''
assert m.count(needle)==2
m=m.replace(needle,needle+'\n    siglum_io_read_pending_maps();')
flush='''
extern void siglum_preview_resource_event(int event);
static void siglum_io_read_pending_maps(void) {
    if (siglum_io_maps_reading || fm_file || !mitem) return;
    siglum_io_maps_reading = 1;
    while (siglum_io_maps_head) {
        siglum_io_map_node *node = siglum_io_maps_head;
        siglum_io_maps_head = node->next;
        if (!siglum_io_maps_head) siglum_io_maps_tail = NULL;
        siglum_io_maps_count--;
        siglum_preview_resource_event(1);
        process_map_item(node->command, MAPFILE);
        xfree(node->command);
        xfree(node);
    }
    siglum_io_maps_reading = 0;
}
'''
m=m.replace('void pdfmapfile(integer t)',flush+'\nvoid pdfmapfile(integer t)',1)
for signature in ['void pdfmapfile(integer t)', 'void pdfmapline(integer t)', 'void pdfmaplinesp(void)']:
    opener=signature+'\n{'
    assert opener in m
    m=m.replace(opener,opener+'\n    siglum_io_read_pending_maps();',1)
# Normally consumed before the first font use. Also release unconsumed paths
# for failed jobs and documents which never use a mapped font.
needle='void fm_free(void)\n{'
cleanup='''
    while (siglum_io_maps_head) {
        siglum_io_map_node *node = siglum_io_maps_head;
        siglum_io_maps_head = node->next;
        xfree(node->command);
        xfree(node);
    }
    siglum_io_maps_tail = NULL;
    siglum_io_maps_count = 0;
    siglum_io_maps_reading = 0;
'''
assert needle in m;m=m.replace(needle,needle+cleanup,1)
(out/'mapfile.c').write_text(m)
(out/'pdftex-live-maps.patch').write_text(''.join(difflib.unified_diff(original_map.splitlines(True),m.splitlines(True),fromfile='a/source/texlive/texk/web2c/pdftexdir/mapfile.c',tofile='b/source/texlive/texk/web2c/pdftexdir/mapfile.c')))
link=json.loads(args.base_commands.read_text())[-1]
for i,arg in enumerate(link):
 if arg=='/work/build/wasm/texlive/texk/kpathsea/.libs/libkpathsea.a':link[i]='/out/libkpathsea.a'
 if arg=='/work/build/wasm/texlive/texk/web2c/busytex_libpdftex.a':link[i]='/out/busytex_libpdftex.a'
 if arg.startswith('-sEXPORTED_FUNCTIONS='):
  exports=json.loads(arg.split('=',1)[1]);exports += ['_siglum_io_api_version', '_siglum_io_register_file', '_siglum_io_queue_map'];link[i]='-sEXPORTED_FUNCTIONS='+json.dumps(exports)
(out/'link-command.json').write_text(json.dumps(link,indent=2)+'\n')
(out/'source-provenance.json').write_text(json.dumps({'originalSource':str(native/'source/texlive/texk/kpathsea/tex-file.c'),'originalSha256':hashlib.sha256(original.encode()).hexdigest(),'patchedSha256':hashlib.sha256(s.encode()).hexdigest(),'mapSourceSha256':hashlib.sha256(original_map.encode()).hexdigest(),'patchedMapSha256':hashlib.sha256(m.encode()).hexdigest(),'baseRuntimeSha256':hashlib.sha256((args.base_runtime/'pdftex.wasm').read_bytes()).hexdigest()},indent=2)+'\n')
