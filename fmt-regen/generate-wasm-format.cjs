#!/usr/bin/env node
// Generate TeX format files using WASM binary
// This ensures format files have compatible 32-bit memory layout

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const vm = require('vm');

const BUNDLES_DIR = path.join(__dirname, '../../packages/bundles');
const WASM_DIR = path.join(__dirname, '../build/wasm');
const OUTPUT_DIR = __dirname;

// Load Emscripten module by evaluating in a sandbox that fakes a worker environment
function loadEmscriptenModule(jsPath) {
    const jsCode = fs.readFileSync(jsPath, 'utf8');
    const moduleName = path.basename(jsPath, '.js');

    // Create a Node.js environment sandbox (NOT worker environment!)
    // The key insight: pdftex.js checks `typeof process == 'object'` to detect Node.js
    // Without process, it falls back to worker mode which fails in Node.js
    const sandbox = {
        // CommonJS exports
        module: { exports: {} },
        exports: {},
        require: require,  // Node.js require
        define: undefined,  // Disable AMD

        // Node.js environment (critical for Emscripten to detect Node.js correctly)
        process: process,
        __filename: jsPath,
        __dirname: path.dirname(jsPath),
        Buffer: Buffer,

        // DO NOT include importScripts - that would trigger ENVIRONMENT_IS_WORKER
        // which overrides Node.js detection and breaks file loading

        // Provide global objects that might be needed
        console: console,
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        setInterval: setInterval,
        clearInterval: clearInterval,

        // WebAssembly is needed
        WebAssembly: WebAssembly,

        // Uint8Array and other typed arrays
        Uint8Array: Uint8Array,
        Int8Array: Int8Array,
        Uint16Array: Uint16Array,
        Int16Array: Int16Array,
        Uint32Array: Uint32Array,
        Int32Array: Int32Array,
        Float32Array: Float32Array,
        Float64Array: Float64Array,
        BigInt64Array: BigInt64Array,
        BigUint64Array: BigUint64Array,
        DataView: DataView,
        ArrayBuffer: ArrayBuffer,
        SharedArrayBuffer: SharedArrayBuffer,

        // Other globals
        Error: Error,
        TypeError: TypeError,
        Object: Object,
        Array: Array,
        String: String,
        Number: Number,
        Boolean: Boolean,
        Symbol: Symbol,
        Promise: Promise,
        Proxy: Proxy,
        Reflect: Reflect,
        JSON: JSON,
        Math: Math,
        Date: Date,
        RegExp: RegExp,
        Map: Map,
        Set: Set,
        WeakMap: WeakMap,
        WeakSet: WeakSet,
        Atomics: Atomics,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        URL: URL,
        URLSearchParams: URLSearchParams,
        Blob: Blob,

        // Make sure eval is available (some modules use it)
        eval: eval,
        Function: Function,

        // Performance API
        performance: {
            now: () => Date.now(),
            timing: { navigationStart: Date.now() }
        },
    };

    // Set self to point to sandbox itself (workers have self === globalThis)
    sandbox.self = sandbox;
    sandbox.globalThis = sandbox;

    vm.runInNewContext(jsCode, sandbox);
    return sandbox.module.exports || sandbox[moduleName];
}

// TeX environment configuration (same as worker.js)
function configureTexEnvironment(ENV) {
    ENV['TEXMFCNF'] = '/texlive/texmf-dist/web2c';
    ENV['TEXMFROOT'] = '/texlive';
    ENV['TEXMFDIST'] = '/texlive/texmf-dist';
    ENV['TEXMFVAR'] = '/texlive/texmf-dist/texmf-var';
    ENV['TEXMFSYSVAR'] = '/texlive/texmf-dist/texmf-var';
    ENV['TEXMFSYSCONFIG'] = '/texlive/texmf-dist';
    ENV['TEXMFLOCAL'] = '/texlive/texmf-dist';
    ENV['TEXMFHOME'] = '/texlive/texmf-dist';
    ENV['TEXMFCONFIG'] = '/texlive/texmf-dist';
    ENV['TEXMFAUXTREES'] = '';
    ENV['TEXMF'] = '/texlive/texmf-dist';
    ENV['TEXMFDOTDIR'] = '.';
    ENV['TEXINPUTS'] = '.:/texlive/texmf-dist/tex/latex//:/texlive/texmf-dist/tex/generic//:/texlive/texmf-dist/tex//:';
    ENV['T1FONTS'] = '.:/texlive/texmf-dist/fonts/type1//';
    ENV['ENCFONTS'] = '.:/texlive/texmf-dist/fonts/enc//';
    ENV['TFMFONTS'] = '.:/texlive/texmf-dist/fonts/tfm//';
    ENV['VFFONTS'] = '.:/texlive/texmf-dist/fonts/vf//';
    ENV['TEXFONTMAPS'] = '.:/texlive/texmf-dist/fonts/map/dvips//:/texlive/texmf-dist/fonts/map/pdftex//:/texlive/texmf-dist/texmf-var/fonts/map//';
    ENV['TEXFORMATS'] = '.:/texlive/texmf-dist/texmf-var/web2c//';
}

// Simple VFS helper
function ensureDir(FS, dirPath) {
    const parts = dirPath.split('/').filter(p => p);
    let current = '';
    for (const part of parts) {
        current += '/' + part;
        try {
            FS.stat(current);
        } catch (e) {
            try {
                FS.mkdir(current);
            } catch (e2) {}
        }
    }
}

function mountFile(FS, filePath, data) {
    const dirPath = filePath.substring(0, filePath.lastIndexOf('/'));
    ensureDir(FS, dirPath);
    FS.writeFile(filePath, data);
}

// Load and decompress bundle
function loadBundle(bundleName) {
    const dataPath = path.join(BUNDLES_DIR, `${bundleName}.data.gz`);
    const metaPath = path.join(BUNDLES_DIR, `${bundleName}.meta.json`);

    if (!fs.existsSync(dataPath)) {
        console.log(`Bundle not found: ${bundleName}`);
        return null;
    }

    const compressed = fs.readFileSync(dataPath);
    const data = zlib.gunzipSync(compressed);
    const meta = fs.existsSync(metaPath) ? JSON.parse(fs.readFileSync(metaPath, 'utf8')) : null;

    console.log(`Loaded bundle ${bundleName}: ${(data.length / 1024 / 1024).toFixed(2)} MB`);
    return { data, meta };
}

// Load file manifest
function loadManifest() {
    const manifestPath = path.join(BUNDLES_DIR, 'file-manifest.json');
    return JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
}

// Mount bundle files to VFS
function mountBundle(FS, bundleName, bundleData, manifest, meta) {
    let mounted = 0;

    // Get files from manifest for this bundle
    for (const [filePath, info] of Object.entries(manifest)) {
        if (info.bundle === bundleName) {
            const content = bundleData.slice(info.start, info.end);
            mountFile(FS, filePath, new Uint8Array(content));
            mounted++;
        }
    }

    // Also check bundle-specific meta
    if (meta?.files) {
        for (const fileInfo of meta.files) {
            const fullPath = `${fileInfo.path}/${fileInfo.name}`;
            const content = bundleData.slice(fileInfo.start, fileInfo.end);
            mountFile(FS, fullPath, new Uint8Array(content));
            mounted++;
        }
    }

    console.log(`Mounted ${mounted} files from ${bundleName}`);
    return mounted;
}

// Generate ls-R file
function generateLsR(FS, basePath) {
    const dirContents = new Map();

    function scanDir(dirPath) {
        try {
            const contents = FS.readdir(dirPath);
            const files = [];
            const subdirs = [];

            for (const name of contents) {
                if (name === '.' || name === '..') continue;
                const fullPath = `${dirPath}/${name}`;
                try {
                    const stat = FS.stat(fullPath);
                    if (FS.isDir(stat.mode)) {
                        subdirs.push(name);
                        scanDir(fullPath);
                    } else {
                        files.push(name);
                    }
                } catch (e) {}
            }

            dirContents.set(dirPath, { files, subdirs });
        } catch (e) {}
    }

    scanDir(basePath);

    const output = ['% ls-R -- filename database.', '% Created by WASM format generator', ''];

    function outputDir(dirPath) {
        const contents = dirContents.get(dirPath);
        if (!contents) return;
        output.push(`${dirPath}:`);
        contents.files.sort().forEach(f => output.push(f));
        contents.subdirs.sort().forEach(d => output.push(d));
        output.push('');
        contents.subdirs.sort().forEach(subdir => outputDir(`${dirPath}/${subdir}`));
    }

    outputDir(basePath);
    const lsRContent = output.join('\n');
    FS.writeFile(`${basePath}/ls-R`, lsRContent);
    console.log(`Generated ls-R with ${dirContents.size} directories`);
}

async function main() {
    const engine = process.argv[2] || 'pdflatex';
    console.log(`=== Generating ${engine} format using WASM ===\n`);

    // Determine which WASM to use
    const wasmName = engine.includes('xelatex') ? 'xetex' :
                     engine.includes('lualatex') ? 'busytex' : 'pdftex';

    const wasmPath = path.join(WASM_DIR, `${wasmName}.wasm`);
    const jsPath = path.join(WASM_DIR, `${wasmName}.js`);

    if (!fs.existsSync(wasmPath)) {
        console.error(`WASM not found: ${wasmPath}`);
        process.exit(1);
    }

    console.log(`Using WASM: ${wasmName}`);
    console.log(`WASM size: ${(fs.statSync(wasmPath).size / 1024 / 1024).toFixed(2)} MB\n`);

    // Load WASM module
    const wasmBinary = fs.readFileSync(wasmPath);
    const wasmModule = await WebAssembly.compile(wasmBinary);

    // Load the JS wrapper using vm sandbox
    const moduleFactory = loadEmscriptenModule(jsPath);

    // Configure environment
    const ENV = {};
    configureTexEnvironment(ENV);

    // Create module instance
    const moduleConfig = {
        thisProgram: `/bin/${wasmName}`,
        noInitialRun: true,
        noExitRuntime: true,
        ENV: ENV,
        instantiateWasm: (imports, successCallback) => {
            WebAssembly.instantiate(wasmModule, imports).then(instance => {
                successCallback(instance);
            });
            return {};
        },
        print: (text) => console.log('[OUT]', text),
        printErr: (text) => console.error('[ERR]', text),
        locateFile: (path) => path,
    };

    console.log('Initializing WASM module...');
    const Module = await moduleFactory(moduleConfig);
    const FS = Module.FS;

    // Create /bin directory
    try { FS.mkdir('/bin'); } catch (e) {}
    try { FS.writeFile(`/bin/${wasmName}`, ''); } catch (e) {}

    // Add helper function
    Module.setPrefix = function(prefix) {
        Module.thisProgram = '/bin/' + prefix;
    };

    Module.callMainWithRedirects = function(args = [], print = false) {
        Module.do_print = print;
        Module.output_stdout = '';
        Module.output_stderr = '';
        if (args.length > 0) Module.setPrefix(args[0]);
        console.log('Calling main with args:', args);
        console.log('thisProgram:', Module.thisProgram);
        const exit_code = Module.callMain(args);
        if (Module._flush_streams) Module._flush_streams();
        return { exit_code, stdout: Module.output_stdout, stderr: Module.output_stderr };
    };

    console.log('WASM module ready\n');

    // Load manifest
    const manifest = loadManifest();

    // Load required bundles for format generation
    // We need: core, l3, utils, fonts-cm, tex-generic, babel (has hyphen.tex with US English patterns)
    const bundlesToLoad = ['core', 'l3', 'utils', 'fonts-cm', 'tex-generic', 'babel'];

    console.log('Loading bundles...');
    for (const bundleName of bundlesToLoad) {
        const bundle = loadBundle(bundleName);
        if (bundle) {
            mountBundle(FS, bundleName, bundle.data, manifest, bundle.meta);
        }
    }

    // Create minimal US-English-only hyphen.cfg to avoid loading German/other languages
    // This overrides babel's multi-language hyphen.cfg
    const minimalHyphenCfg = `% Minimal hyphen.cfg - US English only
% This avoids loading missing language patterns during format generation
\\message{Loading minimal hyphen.cfg (US English only)}

% Load US English hyphenation patterns
\\language=0
\\input{hyphen.tex}

% Define language aliases
\\chardef\\l@english=0
\\chardef\\l@USenglish=0
\\chardef\\l@usenglish=0
\\chardef\\l@american=0

% Create nohyphenation language with no patterns
\\newlanguage\\l@nohyphenation

\\endinput
`;

    // Write minimal hyphen.cfg to override babel's version
    console.log('Creating minimal hyphen.cfg for US English only...');
    FS.writeFile('/texlive/texmf-dist/tex/generic/babel/hyphen.cfg', minimalHyphenCfg);

    // Generate ls-R
    generateLsR(FS, '/texlive/texmf-dist');

    // Verify critical files exist
    const criticalFiles = [
        '/texlive/texmf-dist/web2c/texmf.cnf',
        '/texlive/texmf-dist/tex/latex/base/latex.ltx',
        '/texlive/tex/latex/latexconfig/pdflatex.ini',
        '/texlive/tex/generic/tex-ini-files/pdftexconfig.tex',
    ];

    console.log('\nVerifying critical files:');
    for (const file of criticalFiles) {
        try {
            const stat = FS.stat(file);
            console.log(`  ✓ ${file} (${stat.size} bytes)`);
        } catch (e) {
            console.log(`  ✗ ${file} - NOT FOUND`);
        }
    }

    // First, test if pdfTeX can run at all
    console.log('\n=== Testing pdfTeX --version ===\n');

    try {
        const versionResult = Module.callMainWithRedirects(['pdftex', '--version']);
        console.log(`Version test exit code: ${versionResult.exit_code}`);
        if (versionResult.stdout) console.log(`stdout: ${versionResult.stdout}`);
        if (versionResult.stderr) console.log(`stderr: ${versionResult.stderr}`);
    } catch (e) {
        console.log(`Version test error: ${e.message}`);
    }

    // Run format generation
    console.log(`\n=== Running ${engine} -ini ===\n`);

    let result;
    if (engine === 'pdflatex' || engine === 'pdftex') {
        // Copy all required ini files to root directory for format generation
        const iniFiles = [
            '/texlive/tex/latex/latexconfig/pdflatex.ini',
            '/texlive/tex/generic/tex-ini-files/pdftexconfig.tex',
            '/texlive/tex/generic/tex-ini-files/etex.src',
            '/texlive/tex/generic/etex/etex.sty',
        ];

        for (const iniPath of iniFiles) {
            try {
                const data = FS.readFile(iniPath);
                const fileName = iniPath.substring(iniPath.lastIndexOf('/') + 1);
                FS.writeFile('/' + fileName, data);
                console.log(`Copied ${fileName} to / (${data.length} bytes)`);
            } catch (e) {
                console.log(`Failed to copy ${iniPath}: ${e.message}`);
            }
        }

        // pdflatex format generation - use pdftex with -etex for e-TeX extensions
        // Note: pdftex.wasm doesn't have a separate pdfetex binary, but pdftex has e-TeX built in
        result = Module.callMainWithRedirects([
            'pdftex', '-ini', '-etex', '-interaction=nonstopmode',
            '-jobname=pdflatex', '/pdflatex.ini'
        ]);
    } else if (engine === 'latex') {
        result = Module.callMainWithRedirects([
            'pdfetex', '-ini', '-etex', '-progname=latex',
            '*latex.ini'
        ]);
    } else if (engine === 'pdftex') {
        result = Module.callMainWithRedirects([
            'pdftex', '-ini', '-etex',
            '*pdftex.ini'
        ]);
    } else if (engine === 'etex') {
        result = Module.callMainWithRedirects([
            'pdfetex', '-ini', '-etex',
            '*etex.ini'
        ]);
    }

    console.log(`\nExit code: ${result.exit_code}`);

    // Always list files in / to see what was created
    console.log('\nFiles in /:');
    try {
        const files = FS.readdir('/');
        files.forEach(f => {
            if (f === '.' || f === '..') return;
            try {
                const stat = FS.stat('/' + f);
                if (!FS.isDir(stat.mode)) {
                    console.log(`  ${f} (${stat.size} bytes)`);
                }
            } catch (e) {}
        });
    } catch (e) {
        console.log('  Error listing /:', e.message);
    }

    // Try to read any log file
    const possibleLogs = ['pdflatex.log', 'pdftex.log', 'pdfetex.log', 'texput.log'];
    for (const logName of possibleLogs) {
        try {
            const logData = FS.readFile('/' + logName, { encoding: 'utf8' });
            console.log(`\n=== ${logName} ===`);
            console.log(logData.slice(0, 2000));
        } catch (e) {}
    }

    // Try to extract format file even on non-zero exit (font warnings cause exit=1)
    const fmtName = `${engine}.fmt`;
    try {
        const fmtData = FS.readFile(`/${fmtName}`);
        if (fmtData && fmtData.length > 1000000) { // Sanity check - format should be > 1MB
            const outputPath = path.join(OUTPUT_DIR, fmtName);
            fs.writeFileSync(outputPath, fmtData);
            console.log(`\n✓ Format file written: ${outputPath}`);
            console.log(`  Size: ${(fmtData.length / 1024 / 1024).toFixed(2)} MB`);

            // Verify header
            const header = fmtData.slice(0, 16);
            const headerStr = Buffer.from(header).toString('ascii').replace(/\0/g, ' ');
            console.log(`  Header: ${headerStr}`);
        } else {
            console.error(`Format file too small or missing: ${fmtData?.length || 0} bytes`);
        }
    } catch (e) {
        console.error(`Failed to read format file: ${e.message}`);
    }

    if (result.exit_code !== 0) {
        console.error('\nNote: Exit code was non-zero (likely font warnings, format may still be valid)');

        // Try to read log file
        try {
            const logData = FS.readFile(`/${engine}.log`, { encoding: 'utf8' });
            console.log('\n=== Log file (last 100 lines) ===');
            const lines = logData.split('\n');
            console.log(lines.slice(-100).join('\n'));
        } catch (e) {}
    }
}

main().catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
