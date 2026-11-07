# Same-stack runtime input experiment

This recipe adds an optional Kpathsea host callback to the existing checkpoint
pdfTeX build. Normal project and TeX-tree lookup happens first. A missing runtime
file can then be resolved through the SDK's ordinary package/range provider and
registered in Kpathsea without discarding the current TeX stack.

The browser adapter uses one bounded 256 KiB mailbox. It requires an isolated
worker and SharedArrayBuffer; unsupported environments retain the normal async
resolver and full-build fallback. The mailbox is transport, not a second TeX
heap or a retained shared package cache.

New package font maps are queued and consumed by pdfTeX's normal font-map reader
before its next lookup. They are not read recursively inside Kpathsea. Ordinary
map precedence and the existing native resource-change guard remain in effect.
There are no package-name or font-family exceptions.

Prepare against a completed checkpoint/font-finalization build:

```sh
python3 prepare.py --work /path/to/busytex \
  --base-runtime /path/to/base/runtime \
  --base-commands /path/to/base/commands.json \
  --output /path/to/output
```

Mount the fork read-only at `/work`, this recipe at `/recipe`, and the prepared
output at `/out`. Run `python3 /recipe/build-inside.py` in the pinned Emscripten
image used by the base build. The tested image is
`emscripten/emsdk@sha256:e856cd59d54fd143366c2df314043d63a1ca23ab43521e0f30f9d9a7ce6d43e0`
with platform `linux/amd64`. It is an offline strict relink of the existing
libraries, replacing only the Kpathsea input and pdfTeX map objects. Commands,
toolchain identity, patches, and source/artifact SHA-256 files accompany output.
Do not combine objects from different toolchains or TeX source revisions.

This is a local prototype. Do not substitute its artifacts into a release until
the browser, offline, checkpoint, font-map, and full-build comparisons pass.

Native font-map ordering is covered by actual editor regressions for hidden
package loading, map replacement, map removal, and direct map-file removal.
Explicit Kpathsea font-map requests keep ownership of their TeX directives;
automatic package-map queues are drained before authored setters and lookups.
