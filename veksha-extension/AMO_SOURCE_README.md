# Veksha Firefox extension — reviewer build instructions

This archive contains the complete, unobfuscated source used to produce the
submitted Firefox extension. The generated package is not included in the
source archive.

## Build environment

- Node.js 24.x (the project also supports Node.js 18+)
- npm 11.x
- No globally installed build tools are required
- Network access is required only by `npm ci` to download dependencies from
  the official npm registry

## Reproduce the submitted package

From the directory containing this file:

```bash
npm ci
npm run build:firefox
```

The unpacked Firefox extension is written to `dist/firefox`. To reproduce the
uploaded ZIP with standard Info-ZIP tools:

```bash
cd dist/firefox
zip -q -r ../../veksha-firefox.zip .
```

The production backend origin is declared in `manifest.json` and
`src/shared/config.ts`. Localhost origins are injected only into watch-mode
development builds and are absent from `npm run build:firefox` output.

Vite bundles TypeScript and React. `scripts/sync-assets.mjs` copies the OCR
worker, WebAssembly cores, and language models from the installed dependencies
and checked-in `source` directory before Vite runs. No code is downloaded or
executed remotely by the installed extension.
