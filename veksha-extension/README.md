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
npm run release          # both store ZIPs + AMO source ZIP → artifacts/
npm run dev              # watch mode, launches Zen (Firefox build)
npm run dev:brave        # watch mode, launches Brave (Chrome build)
npm run dev:zen          # watch mode, launches Zen (Firefox build)
npm run dev:chrome       # watch mode, launches stock Chrome
npm run dev:firefox      # watch mode, launches stock Firefox
```

Watch mode auto-launches the browser via web-ext with a persistent profile and
reloads the extension on rebuild. `dev:brave`/`dev:zen` locate the executable
on the current OS (`scripts/browser-binary.mjs`: PATH, then the usual macOS /
Linux / Windows install locations); when that browser is not installed they
fall back to the stock browser of the same family with a warning. For a
non-standard install set `BRAVE_BINARY` / `ZEN_BINARY` to its path, or pass
one explicitly: `node scripts/build.mjs firefox --watch --binary <path>`.

Load in Chrome: `chrome://extensions` → Developer mode → Load unpacked →
select `veksha-extension/dist/chrome`.

Load in Firefox: `about:debugging#/runtime/this-firefox` → Load Temporary
Add-on → select `dist/firefox/manifest.json`. (Permanent installs need the
add-on signed by AMO; the `browser_specific_settings.gecko.id` is set in
`manifest.json`.)

`npm run dev`, `dev:zen`, and `dev:firefox` automatically use the local backend
at `http://127.0.0.1:8000`. Production builds use `https://veksha.app`.
Development credentials use separate storage keys, so a production token in
the persistent browser profile cannot cause local `401` responses.
`npm run release` removes the previous `artifacts/` directory, performs clean
production builds, validates the generated manifests, excludes localhost
permissions and source maps, and creates Chrome, Firefox, and Firefox reviewer
source archives. See `AMO_SOURCE_README.md` for the exact reproducible build
instructions included with the AMO source upload.

## Browser differences

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
                   reminder alarms, context menu, first-review nudge
src/capture/       one-shot screenshot crop workspace for image/PDF translation
src/content/       selection translate popup, Reading Coach, YouTube
                   subtitles integration, in-page reminder overlay
src/popup/         popup app: translator, topics, training
                   and lesson overlays, statistics, settings, onboarding
src/training/      standalone training page (full tab)
src/lesson/        standalone lesson page (full tab)
src/shared/        api client, config, types, i18n, speech helpers,
                   platform adapters
design/            brand-art generator (render.mjs): squirrel logo/icons,
                   mascot GIF frames, popup background pattern
```

## Google sign-in (optional)

The onboarding screen shows "Continue with Google" when
`CONFIG.GOOGLE_CLIENT_ID` (src/shared/config.ts) is set. Local setup:

1. Google Cloud Console → APIs & Services → Credentials → Create credentials
   → OAuth client ID → type **Web application** (configure the consent screen
   first if asked).
2. Add the backend HTTPS callback
   `https://veksha.app/api/auth/google/callback`
   as the client's single
   **Authorized redirect URI**. Do not add `chromiumapp.org`, `allizom.org`,
   or custom schemes such as `orion-oauth://`.
3. Put the client ID into `CONFIG.GOOGLE_CLIENT_ID`. Configure the backend
   with the same `GOOGLE_CLIENT_ID`, its `GOOGLE_CLIENT_SECRET`, and the exact
   callback as `GOOGLE_OAUTH_REDIRECT_URI`.

Flow: the popup asks the background (`VEKSHA_GOOGLE_SIGNIN` /
`VEKSHA_GOOGLE_LINK`) to start a backend Authorization Code flow. The
background opens Google in a normal tab and polls the backend with a separate
single-use secret; Google returns only to the HTTPS backend callback. This
avoids every browser-specific extension callback and works across Chrome,
Brave, Vivaldi, Firefox, Zen, Orion, and other compatible browsers. The
background persists credentials (and the link outcome) to storage so the
next popup open picks them up even if the original popup closed. An existing
linked account is recovered with its vocabulary; a new Google user continues
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
