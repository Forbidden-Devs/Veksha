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

- Chrome's MV3 background is a service worker with no DOM, so OCR runs in an
  offscreen document (`src/offscreen/`). Firefox has no `offscreen` API, but
  its background is an event page with DOM access — it runs the same capture
  controller (`src/shared/capture.ts`) directly. The split is decided at
  build time via the `__BROWSER__` constant.
- Firefox MV3 treats `<all_urls>` host permission as opt-in: users must grant
  site access in the extension's Permissions settings (or per-site via the
  toolbar icon) before content scripts run everywhere.
- Local dev against a plain-HTTP backend: Firefox blocks `ws://` from
  extension pages as mixed content even for 127.0.0.1
  (NS_ERROR_CONTENT_BLOCKED in the training/lesson windows). `npm run
  dev:zen` / `dev:firefox` set the profile pref
  `network.websocket.allowInsecureFromHTTPS=true` automatically; when
  loading `dist/firefox` manually, flip that pref in `about:config`
  yourself. Production (`wss://`) is unaffected.

## Source map

```
src/background/    background (Chrome: service worker, Firefox: event page):
                   reminder alarms, context menu, OCR routing,
                   first-review nudge
src/content/       selection translate popup, immersion mode, YouTube
                   subtitles integration, in-page reminder overlay
src/popup/         popup app: chat (assistant/translator), topics, training
                   and lesson overlays, statistics, settings, onboarding
src/training/      standalone training page (full tab)
src/lesson/        standalone lesson page (full tab)
src/offscreen/     offscreen document (Chrome only): hosts shared/capture
src/shared/        api client, config, types, i18n, speech helpers,
                   capture controller (OCR via tesseract.js)
design/            brand-art generator (render.mjs): squirrel logo/icons,
                   mascot GIF frames, popup background pattern
```

## Google sign-in (optional)

The onboarding screen shows "Continue with Google" when
`CONFIG.GOOGLE_CLIENT_ID` (src/shared/config.ts) is set. Local setup:

1. Google Cloud Console → APIs & Services → Credentials → Create credentials
   → OAuth client ID → type **Web application** (works for Chrome and
   Firefox; configure the consent screen first if asked).
2. Find your redirect URI: open the popup's devtools console and run
   `chrome.identity.getRedirectURL()` — e.g.
   `https://<extension-id>.chromiumapp.org/` in Chrome/Brave or
   `https://<hash>.extensions.allizom.org/` in Firefox/Zen. Add both as
   **Authorized redirect URIs** of the client. (Unpacked extension IDs are
   derived from the install path, so they are stable per machine.)
3. Put the client ID into `CONFIG.GOOGLE_CLIENT_ID` and start the backend
   with the same id: `export GOOGLE_CLIENT_ID="<id>.apps.googleusercontent.com"`.

Flow: the popup asks the background (`VEKSHA_GOOGLE_SIGNIN` /
`VEKSHA_GOOGLE_LINK`) to run `chrome.identity.launchWebAuthFlow`
(shared/googleAuth.ts) — the popup dies as soon as the OAuth window takes
focus, so the flow must live in the background. The obtained ID token
(implicit flow, nonce-checked) goes to `POST /api/auth/google`, which
verifies it server-side and returns the regular bearer token; the background
persists credentials (and the link outcome) to storage so the next popup
open picks them up even if the original one closed. An existing linked
account is recovered with its vocabulary; a new Google user continues
onboarding.

## Identity

During onboarding the user picks a display name; `POST /api/auth/register`
creates the account under a generated internal id (`username`, e.g.
`u_3f9c2a7b1d`) and returns it with a bearer token, both stored in
`chrome.storage.local`. The display name lives in settings and is editable
on the Settings screen; the id never changes. All backend requests carry
`Authorization: Bearer <token>`; WebSockets authenticate with a first
message `{"type": "auth", "token": "..."}`. Without a linked Google
account, clearing extension storage orphans the account.

## Known limitations

- `BACKEND_URL` and `host_permissions` (manifest.json) must be kept in sync
  when the backend moves.
- `chrome.action.openPopup()` on notification click does not work in every
  Chrome version; the notification then simply closes.
