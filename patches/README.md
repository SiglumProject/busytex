# Compiler source patches

The source preparation target applies these patches idempotently. A fresh source
must accept the forward patch; an already patched tree must accept the reverse
check. An unrecognized partial change rejects that patch without applying it.

- `pdftex-type1-preflight.patch` lets the host resolve missing Type1 resources
  before final font output. The host must resume the same engine state or use
  the ordinary full-build fallback.
- `xetex-icu-converters.patch` separates ICU converter initialization. A reduced
  ICU data build can lack the legacy Macintosh converter; carrying its error
  status into independent Unicode converter calls made XeTeX abort while reading
  font names. Unicode converters remain required. Macintosh name records are
  skipped only when their converter is unavailable. This changes no font-family
  mapping and adds no JavaScript font workaround.

The companion SDK's font-inventory and named-font browser regressions exercise font-name lookup and Unicode
input normalization. Run it with the actual compiled XeLaTeX/xdvipdfmx runtime
and its matching TeX tree, including a fresh cached/offline browser check when
used through the browser SDK. A successful pdfTeX-only build does not verify
this regression. Compiler artifacts need their own reproducible, matching build;
an older local binary is not a substitute for a current release.
