# Veksha Web

The Veksha study app as a standalone web page (PWA-installable): chat
assistant, trainings, topic lessons, statistics, and settings. It reuses the
extension popup source tree directly — see `src/main.tsx`, which imports
`App` from `../veksha-extension/src/popup/`.

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

The backend URL comes from `veksha-extension/src/shared/config.ts`
(`BACKEND_URL`). Remember to include the web origin in the backend's
`CORS_ALLOW_ORIGINS`.

## How platform differences are handled

`veksha-extension/src/shared/platform.ts` abstracts the extension-only APIs:

- `chrome.storage.local` → `localStorage` on the web (auth token, language
  caches, UI flags).
- Trainings/lessons: the extension popup injects them into the active tab;
  on the web they render as in-app overlays (see `webOverlay` in `App.tsx`).
- Immersion toggle is hidden on the web (it requires a content script).
- Tutorial screenshots fall back to placeholders (images are not bundled).

## Not done yet

- No service worker: the manifest makes the app installable, but there is no
  offline support (training requires the backend anyway).
- Accounts created in the extension and on the web are separate unless you
  copy the token; a proper login flow (Google OAuth) is the planned fix.
