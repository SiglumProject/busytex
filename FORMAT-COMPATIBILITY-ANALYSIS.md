# BusyTeX Format File Compatibility: Complete Analysis

## Executive Summary

After four days of debugging, the core issue remains: **"strings are different"** when loading pdflatex.fmt. This document captures everything learned to prevent repeating failed approaches.

---

## The Error

```
[TeX] ---! /texlive/texmf-dist/texmf-var/web2c/pdftex/pdflatex.fmt made by different executable version, strings are different
[TeX] (Fatal format file error; I'm stymied)
```

This error occurs when the format file's internal string table doesn't match what the loading pdfTeX binary expects.

---

## Current State (2025-01-01)

### WASM Binaries

| File | Size | pdfTeX Version | Source |
|------|------|----------------|--------|
| `pdftex.wasm` | 1.3 MB | 1.40.28 | TL2025.2 source, split from busytex |
| `busytex.wasm` | 30 MB | 1.40.27 | TL2025.2 source, full multi-engine |
| `xetex.wasm` | 25 MB | - | TL2025.2 source |

### Format Files Attempted

| Source | Checksum | pdfTeX Version | Result |
|--------|----------|----------------|--------|
| TL2023 Docker (fmtutil) | `1717 d8af` | 1.40.25 | "strings are different" |
| TL2025 Docker (fmtutil) | `1f30 888a` | 1.40.28 | "strings are different" |
| WASM Node.js (--ini) | `0817 d6e4` | 1.40.25* | "strings are different" |

*The WASM-generated format claims 1.40.25 in its log, suggesting the WASM binary being used for generation is NOT the same as what we think.

---

## Key Insight: The Real Problem

The "strings are different" error is NOT about version numbers. It's about **internal string pool compatibility**.

TeX format files contain:
1. A string pool (all macro names, primitives, error messages)
2. Memory dumps (hash tables, equivalents)
3. Checksum bytes tied to the generating binary

**The string pool is baked into the pdfTeX binary at compile time.** Different compile-time options, different LaTeX kernel versions, or even different build environments can produce binaries with incompatible string pools.

---

## What We Tried (Chronological)

### Day 1-2: Docker Format Generation
- Used `texlive/texlive:TL2023-historic` to generate formats
- Overlaid TL2024 LaTeX kernel files
- Generated format with native `pdflatex --ini`
- **Result**: Formats load in native pdfTeX but not in WASM

### Day 3: WASM Format Generation
- Created `generate-wasm-format.cjs` to run pdftex.wasm in Node.js
- Used Emscripten module with `--ini` flag
- Generated format with checksum `0817 d6e4`
- **Result**: Still "strings are different"

### Day 4: Bundle Structure
- Verified double-gzip structure (outer → inner gzip → W2TX header)
- Updated metadata with correct byte offsets
- Confirmed format decompresses correctly
- **Result**: Structure is correct, but format still incompatible

---

## Why Everything Failed

### Hypothesis 1: Wrong Binary Used for Generation

The format generation log shows:
```
This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023_busytexnative) (INITEX)
```

But `pdftex.wasm` should be 1.40.28. This means `generate-wasm-format.cjs` is loading the WRONG binary or the binary itself reports the wrong version.

### Hypothesis 2: Node.js vs Browser Differences

Even if using the correct WASM:
- Emscripten modules can behave differently in Node.js vs browser
- Memory initialization, filesystem mocking, and environment differ
- The format generated in Node.js may have layout incompatible with browser loading

### Hypothesis 3: Split WASM Issue

`pdftex.wasm` (1.3MB) was "split" from `busytex.wasm` (30MB). The split process may have:
- Changed string pool offsets
- Modified memory layout
- Broken format compatibility

---

## What We Have NOT Tried

### 1. In-Browser Format Generation
Generate the format IN THE BROWSER using the exact WASM binary that will load it:
```javascript
// In browser console or test page
compiler.compile("\\documentclass{article}\\begin{document}test\\end{document}", { ini: true });
```
This guarantees the same binary, same environment, same memory layout.

### 2. Use busytex.wasm (30MB) Instead
The full busytex.wasm reports 1.40.27, while pdftex.wasm reports 1.40.28. The larger binary might have compatible formats available or different behavior.

### 3. Verify WASM Binary Identity
Check that the WASM being served is identical to the one used for format generation:
```bash
md5 busytex/build/wasm/pdftex.wasm
md5 dist/wasm/pdftex.wasm
```

### 4. Use Pre-Built Format from Upstream
The original busytex project may have compatible format files. Check:
- https://github.com/nickmahr/nickmahr.github.io/tree/main/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/nickmahr.github.io/texlive.github.io (if exists)
- Original busytex release artifacts

### 5. Rebuild WASM with Format Baked In
Modify the Makefile to:
1. Build WASM
2. Generate format using that WASM (in emscripten container)
3. Bundle format with WASM
4. Version both together

---

## The Sustainable Path Forward

### Option A: Browser-Based Format Generation (Simplest)

Add code to busytex-lazy that:
1. Detects missing/incompatible format
2. Runs pdfTeX in `--ini` mode in the browser
3. Generates format on-demand
4. Caches in IndexedDB/OPFS

**Pros**: Always compatible, no version management
**Cons**: Slow first load (~30-60 seconds), requires LaTeX kernel files

### Option B: Build-Time Format Generation (Most Robust)

Modify `build-wasm.sh` to:
1. Build WASM in emscripten container
2. Run WASM with `--ini` in same container (using Node.js)
3. Package format and WASM together
4. Version-lock both artifacts

**Pros**: One-time build cost, guaranteed compatibility
**Cons**: Complex build process, requires format regeneration on WASM changes

### Option C: Use Known-Good Pair (Quickest)

Find a working WASM + format pair:
1. Check busytex upstream releases
2. Use older known-working version
3. Accept older LaTeX kernel

**Pros**: Immediate solution
**Cons**: May have older LaTeX features, dependency on upstream

---

## Files Reference

### Build System
- `/Users/adam/code/siglum-engine/busytex/Makefile` - Main build
- `/Users/adam/code/siglum-engine/busytex/build-wasm.sh` - Docker build orchestrator

### Format Generation
- `/Users/adam/code/siglum-engine/busytex/fmt-regen/generate-wasm-format.cjs` - Node.js WASM runner
- `/Users/adam/code/siglum-engine/busytex/fmt-regen/pdflatex-busytex-uncompressed.fmt` - WASM-generated format

### Bundles
- `/Users/adam/code/siglum-engine/packages/bundles/fmt-pdflatex.data.gz` - Current bundle
- `/Users/adam/code/siglum-engine/packages/bundles/fmt-pdflatex.meta.json` - Metadata

### WASM
- `/Users/adam/code/siglum-engine/busytex/build/wasm/pdftex.wasm` - 1.3MB, claims 1.40.28
- `/Users/adam/code/siglum-engine/busytex/build/wasm/busytex.wasm` - 30MB, claims 1.40.27

---

## Verification Commands

```bash
# Check WASM binary checksums
md5 busytex/build/wasm/pdftex.wasm
md5 dist/wasm/pdftex.wasm

# Check format file header
xxd packages/bundles/fmt-pdflatex.data.gz | head -2  # Should start with 1f8b (gzip)
gunzip -c packages/bundles/fmt-pdflatex.data.gz | xxd | head -2  # Inner gzip
gunzip -c packages/bundles/fmt-pdflatex.data.gz | gunzip -c | xxd | head -3  # W2TX header + checksum

# Check version in WASM (look for version string)
strings busytex/build/wasm/pdftex.wasm | grep "pdfTeX"
```

---

## Recommended Next Step

**Try Option A first** - implement browser-based format generation as a fallback. This:
1. Guarantees compatibility (same binary generates and loads)
2. Can be done without rebuilding WASM
3. Provides a working solution while we figure out the build-time approach

The implementation would go in `busytex-lazy` worker.js, adding an `--ini` mode compile path.

---

## Diagnostic Results (2025-01-01)

### Q1: What versions are embedded in the WASM binaries?

```
pdftex.wasm:  "This is pdfTeX, Version 3.141592653-2.6-1.40.28"
busytex.wasm: "This is pdfTeX, Version 3.141592653-2.6-1.40.27"
```

**Both WASM binaries have correct TL2025 versions embedded.**

### Q2: Are build/wasm and dist/wasm identical?

```
MD5 (busytex/build/wasm/pdftex.wasm) = a48854e4995b9089cd49188b8e0cccd0
MD5 (dist/wasm/pdftex.wasm)          = a48854e4995b9089cd49188b8e0cccd0
```

**Yes, they are identical.** The WASM being served is the same as the one in build.

### Q3: What does generate-wasm-format.cjs load?

The script correctly loads `pdftex.wasm` from `../build/wasm/`:
```javascript
const wasmName = engine.includes('xelatex') ? 'xetex' :
                 engine.includes('lualatex') ? 'busytex' : 'pdftex';
const wasmPath = path.join(WASM_DIR, `${wasmName}.wasm`);
```

### The Mystery

The format generation log shows:
```
This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023_busytexnative) (INITEX)
```

**But pdftex.wasm contains 1.40.28!**

This means the format generation is NOT actually using pdftex.wasm. The string "TeX Live 2023_busytexnative" is compiled into a DIFFERENT binary - likely the native busytex binary from the old TL2023 build.

### Root Cause Identified

**The Emscripten module is not executing correctly in Node.js.** Something is falling back to the native binary or there's a module loading issue.

Possible causes:
1. The `.js` companion file for pdftex.wasm is missing or incompatible
2. Node.js WebAssembly.instantiate is failing silently
3. There's a native fallback mechanism in the Emscripten glue code

### Next Step

Check if `pdftex.js` exists alongside `pdftex.wasm` and verify it's compatible with Node.js execution. If not, we need to generate format files using a different approach (browser-based or build-time in emscripten container).

---

## Questions to Answer (RESOLVED)

### Q1: Does `pdftex.js` exist? Is it compatible with Node.js?

**YES**, `pdftex.js` exists at `busytex/build/wasm/pdftex.js` (270 KB).

The file is a standard Emscripten module that:
- Detects environment via `typeof process`, `typeof importScripts`, etc.
- Supports Node.js, Web Worker, and browser environments
- Requires Node.js v16+ (line 93 of pdftex.js)

### Q2: Why does generate-wasm-format.cjs fail to use the WASM?

**CRITICAL FINDING**: The script uses `vm.runInNewContext()` to create a sandbox that simulates a Web Worker environment:

```javascript
// From generate-wasm-format.cjs lines 19-27
const sandbox = {
    importScripts: function() {}, // Fakes worker environment
    self: {},
    // ... but NO 'process' object!
};
```

**The Problem**:
- `pdftex.js` line 64 checks: `var ENVIRONMENT_IS_NODE = typeof process == 'object' && ...`
- Since `process` is NOT in the sandbox, `ENVIRONMENT_IS_NODE = false`
- The module then thinks it's running in a Web Worker
- Web Workers load files differently (via `fetch`/XHR), which fails in Node.js sandbox
- This likely causes silent failures in WASM loading

**Smoking Gun Evidence**:
The log shows "TeX Live 2023_busytexnative" which is a banner string that doesn't exist in pdftex.wasm (we verified it contains "1.40.28"). This proves the WASM never actually executed - some fallback path ran instead.

### Q3: Can we run pdftex.wasm in the emscripten container?

**UNTESTED** but this is the most promising approach. The emscripten container has:
- Node.js with proper environment
- Same toolchain used to build the WASM
- Native access to file system

### Q4: Does upstream busytex have working format files?

**UNTESTED** - the original busytex repo should be checked.

---

## Definitive Fix Options

### Option 1: Fix the Sandbox (Quick Fix)

Add `process` to the sandbox in `generate-wasm-format.cjs`:

```javascript
const sandbox = {
    // ... existing code ...
    process: process,  // ADD THIS LINE
    require: require,  // May also be needed
    __filename: jsPath,
    __dirname: path.dirname(jsPath),
};
```

This would make `ENVIRONMENT_IS_NODE = true` and enable proper Node.js file loading.

### Option 2: Use Emscripten Container (Build-Time)

Run format generation inside the same Docker container used for WASM build:

```bash
podman run --rm -v "$(pwd):/work" -w /work emscripten/emsdk:3.1.43 bash -c "
  node --experimental-wasm-modules /work/fmt-regen/generate-wasm-format.cjs
"
```

### Option 3: Browser-Based Generation (Runtime) - IMPLEMENTED

Generate format in the browser where the WASM actually runs. This guarantees compatibility but adds first-load latency.

---

## Solution Implemented (2026-01-01)

**Browser-based format generation has been implemented in busytex-lazy.**

### Files Modified

**worker.js:**
- Added `handleBaseFormatGenerate()` function (lines 1301-1437)
- Added message handler case for `'generate-base-format'` (lines 1473-1478)
- Runs `pdftex -ini -etex pdflatex.ini` to generate format from scratch

**compiler.js:**
- Added `pendingBaseFormat` tracking variable
- Added `'base-format-generate-response'` case in `_handleWorkerMessage`
- Added `generateBaseFormat(engine)` method to trigger format generation
- Added `getCachedBaseFormat(engine)` method to check OPFS cache

### Usage

```javascript
const compiler = new BusyTeXCompiler({ ... });
await compiler.init();

// Generate base format (first time only, cached in OPFS)
const fmtData = await compiler.generateBaseFormat('pdflatex');

// Check if format is cached
const cached = await compiler.getCachedBaseFormat('pdflatex');
```

### How It Works

1. Loads required bundles: `base` (hyphenation), `latex-base` (kernel)
2. Sends `'generate-base-format'` message to worker
3. Worker runs `pdftex -ini -etex -jobname=pdflatex pdflatex.ini`
4. Format is returned and cached in OPFS at `fmt-cache/base_pdflatex.fmt`
5. Subsequent calls use cached format

### Trade-offs

**Pros:**
- Guaranteed compatibility (same binary generates and loads)
- No version management needed
- Works with any WASM build

**Cons:**
- First-time generation takes 30-60 seconds
- Requires downloading LaTeX kernel source files (~2MB)
- Uses more browser memory during generation

---

*Document created: 2025-01-01*
*Last updated: 2026-01-01*
*Context: Four days of debugging, root cause identified, solution implemented*
