# Veksha Web

The Veksha mobile study companion as an installable PWA: quick translation
and word capture, vocabulary, spaced-repetition training, topic lessons,
statistics, and settings. It reuses the extension's study screens
but provides its own responsive home screen and mobile navigation.

The browser extension remains the capture surface (selection translate,
immersion, YouTube, OCR); this app is the study surface that works on any
device, including mobile via "Add to Home Screen".

## Run

Requires Node.js 18+.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/
npm run typecheck  # tsc over web + shared popup sources
```

Production uses `https://veksha.app` by default. Set `VITE_BACKEND_URL` at
build time for local, preview, or staging environments. Remember to include
the deployed web origin in the backend's `CORS_ALLOW_ORIGINS`.

## How platform differences are handled

`veksha-extension/src/shared/platform.ts` abstracts the extension-only APIs:

- `chrome.storage.local` → `localStorage` on the web (auth token, language
  caches, UI flags).
- Trainings/lessons: the extension popup injects them into the active tab;
  on the web they render as in-app overlays (see `webOverlay` in `App.tsx`).
- Page capture, immersion, dual subtitles, grammar lens, browsing frequency,
  OCR and AI blocking stay extension-only.
- Tutorial screenshots fall back to placeholders (images are not bundled).
- Google sign-in/linking lets the PWA and extension open the same account.
- A service worker caches the application shell; live learning data still
  requires a connection to the backend.

## Railway

Use the repository root as the service source because the web build imports
shared extension files. Point the service config at `/veksha-web/railway.toml`;
its Docker build and watch paths include both the web app and shared UI source.
The Docker builder is intentional: Railpack cannot infer a Node provider from
the monorepo root, which has no root `package.json`. After assigning a public
domain, add that exact origin to backend `CORS_ALLOW_ORIGINS`.
