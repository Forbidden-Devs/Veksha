# Veksha Extension (Chrome + Firefox, MV3)

React + TypeScript extension built with Vite (`vite-plugin-web-extension`).
One codebase, two build targets; `manifest.json` uses `{{chrome}}.`/`{{firefox}}.`
key prefixes for the parts that differ.

## Build

Requires Node.js 18+.

```bash
npm install
npm run build            # both targets → dist/chrome + dist/firefox
npm run build:chrome     # Chrome only
npm run build:firefox    # Firefox only
npm run dev              # watch mode, launches Brave with the extension loaded
npm run dev:zen          # watch mode, launches Zen (Firefox build)
npm run dev:firefox      # watch mode, launches stock Firefox
```

Watch mode auto-launches the browser via web-ext with a fresh profile and
reloads the extension on rebuild. `dev`/`dev:zen` point at the macOS Brave
and Zen executables; for another machine, adjust the `--binary` path in
package.json (or run `node scripts/build.mjs chrome --watch` for the
default browser of the target family).

Load in Chrome: `chrome://extensions` → Developer mode → Load unpacked →
select `veksha-extension/dist/chrome`.

Load in Firefox: `about:debugging#/runtime/this-firefox` → Load Temporary
Add-on → select `dist/firefox/manifest.json`. (Permanent installs need the
add-on signed by AMO; the `browser_specific_settings.gecko.id` is set in
`manifest.json`.)

Backend URL is configured in `src/shared/config.ts` (`BACKEND_URL`).
`scripts/sync-assets.mjs` copies tesseract/langdata assets into `public/`
before the build (`npm run sync-assets`).

## Browser differences

- Chrome's MV3 background is a service worker with no DOM, so mic capture and
  OCR run in an offscreen document (`src/offscreen/`). Firefox has no
  `offscreen` API, but its background is an event page with DOM access — it
  runs the same capture controller (`src/shared/capture.ts`) directly. The
  split is decided at build time via the `__BROWSER__` constant.
- Firefox may not record `audio/webm`; `src/shared/audio.ts` negotiates the
  container (webm/ogg) and the backend forwards whatever it gets to STT.
- Firefox MV3 treats `<all_urls>` host permission as opt-in: users must grant
  site access in the extension's Permissions settings (or per-site via the
  toolbar icon) before content scripts run everywhere.
- Firefox may prompt for microphone permission on every use unless the user
  ticks "Remember this decision" in the permission popup.

## Source map

```
src/background/    background (Chrome: service worker, Firefox: event page):
                   reminder alarms, context menu, OCR and voice-capture
                   routing, first-review nudge
src/content/       selection translate popup, immersion mode, YouTube
                   subtitles integration, in-page reminder overlay
src/popup/         popup app: chat (assistant/translator), topics, training
                   and lesson overlays, statistics, settings, onboarding
src/training/      standalone training page (full tab)
src/lesson/        standalone lesson page (full tab)
src/offscreen/     offscreen document (Chrome only): hosts shared/capture
src/permission/    microphone-permission helper window
src/shared/        api client, config, types, i18n, speech helpers,
                   capture controller (OCR via tesseract.js, mic recording)
design/            brand-art generator (render.mjs): squirrel logo/icons,
                   mascot GIF frames, popup background pattern
```

## Identity

During onboarding the user picks a `username`; the extension registers it via
`POST /api/auth/register` and stores the returned bearer token in
`chrome.storage.local` (`veksha_token`). All backend requests carry
`Authorization: Bearer <token>`; WebSockets pass `?token=`. There is no
login/recovery yet — clearing extension storage orphans the account.

## Known limitations

- `BACKEND_URL` and `host_permissions` (manifest.json) must be kept in sync
  when the backend moves.
- `chrome.action.openPopup()` on notification click does not work in every
  Chrome version; the notification then simply closes.
