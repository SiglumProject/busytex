'use strict';

const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFileSync, statSync } = require('node:fs');
const { createRequire } = require('node:module');
const { join, resolve } = require('node:path');

const directory = resolve(process.argv[2] ?? __dirname);
const lockName = 'texlive-packages.lock.json';
const manifestName = 'texlive-basic-formats.sha256';
const formatDirectory = 'texmf-dist/texmf-var/web2c';
const formats = ['pdftex/pdflatex.fmt', 'xetex/xelatex.fmt', 'luahbtex/luahblatex.fmt'];

async function smoke() {
  const manifest = readFileSync(join(directory, manifestName), 'utf8');
  const hashes = new Map();
  for (const line of manifest.trim().split('\n')) {
    const entry = /^([a-f0-9]{64})  (\S+)$/.exec(line);
    assert(entry && !hashes.has(entry[2]), 'Invalid format checksum line: ' + line);
    hashes.set(entry[2], entry[1]);
  }

  function verifyHash(name, data) {
    assert(hashes.has(name), 'Missing format checksum: ' + name);
    assert.equal(createHash('sha256').update(data).digest('hex'), hashes.get(name),
      'Format checksum mismatch: ' + name);
  }

  const lock = readFileSync(join(directory, lockName));
  const gluePath = join(directory, 'busytex.js');
  const glue = readFileSync(gluePath);
  const wasm = readFileSync(join(directory, 'busytex.wasm'));
  verifyHash(lockName, lock);
  verifyHash('build/wasm/busytex.js', glue);
  verifyHash('build/wasm/busytex.wasm', wasm);
  assert(statSync(join(directory, 'texlive-basic.data')).size > 0, 'Missing TeX data');
  const { formatVersion } = JSON.parse(lock.toString('utf8'));
  assert.match(formatVersion, /^\d{4}-\d{2}-\d{2}$/);

  // The generated glue is CommonJS even under an enclosing ESM package.
  const glueModule = { exports: {} };
  const assetRequire = createRequire(gluePath);
  new Function('require', 'module', 'exports', '__filename', '__dirname', glue.toString('utf8'))(
    assetRequire, glueModule, glueModule.exports, gluePath, directory,
  );

  const config = {
    noInitialRun: true,
    thisProgram: '/bin/busytex',
    wasmBinary: wasm,
    locateFile: name => join(directory, name),
    preRun: [module => {
      module.ENV.TEXMFCNF = '/texlive/texmf-dist/web2c';
      module.FS.writeFile('/smoke.tex', String.raw`\documentclass{article}
\begin{document}
BusyTeX release smoke test.
\end{document}
`);
    }],
  };

  // Exercise the real data loader and its fallback to local file reads.
  const window = {
    encodeURIComponent,
    location: { pathname: '/' },
    indexedDB: {
      open() {
        const request = {};
        queueMicrotask(() => request.onerror('IndexedDB unavailable in the Node smoke test'));
        return request;
      },
    },
  };
  const loader = readFileSync(join(directory, 'texlive-basic.js'), 'utf8');
  new Function('BusytexPipeline', 'require', 'window', loader)(config, assetRequire, window);

  const instance = await glueModule.exports(config);
  for (const format of formats) {
    const filename = formatDirectory + '/' + format;
    const packaged = '/texlive/' + filename;
    assert(instance.FS.analyzePath(packaged).exists, 'Missing packed format: ' + packaged);
    verifyHash('build/texlive-basic/' + filename, instance.FS.readFile(packaged));
  }

  const status = instance.callMain([
    'pdflatex', '-no-shell-escape', '-halt-on-error', '-interaction=nonstopmode',
    '-fmt=/texlive/' + formatDirectory + '/' + formats[0], '/smoke.tex',
  ]);
  assert.equal(status, 0, 'pdfLaTeX failed');
  const pdf = Buffer.from(instance.FS.readFile('/smoke.pdf'));
  assert.equal(pdf.subarray(0, 5).toString('ascii'), '%PDF-');
  assert.match(pdf.subarray(-32).toString('ascii'), /%%EOF\s*$/);
  const log = instance.FS.readFile('/smoke.log', { encoding: 'utf8' });
  assert(log.includes('LaTeX2e <' + formatVersion + '>'), 'Unexpected LaTeX format');
  console.log(`Verified three packed formats and a ${pdf.length}-byte LaTeX2e ${formatVersion} PDF.`);
}

const watchdog = setTimeout(() => {
  console.error('BusyTeX release smoke timed out');
  process.exit(1);
}, 30_000);

smoke().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(() => clearTimeout(watchdog));
