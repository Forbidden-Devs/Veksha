import { mkdirSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import webExtension from "vite-plugin-web-extension";

// Browser target comes from TARGET_BROWSER (set by scripts/build.mjs); it
// resolves the {{chrome}}./{{firefox}}. keys in manifest.json. Selecting via
// --mode instead would bake the mode string into bundles as NODE_ENV and pull
// in development React (vite-plugin-web-extension#96).
const browser = process.env.TARGET_BROWSER === "firefox" ? "firefox" : "chrome";

// Optional path to the browser executable web-ext launches in watch mode
// (Brave, Zen, …). Set via `scripts/build.mjs --binary <path>`.
const browserBinary = process.env.BROWSER_BINARY;

// Persistent dev profile per launched browser, so the extension keeps its
// storage (auth token, onboarding) and the browser skips first-run setup
// between watch sessions. Keyed by executable name — Zen and stock Firefox
// must not share a profile (version downgrade protection would trip).
const profileKey = (browserBinary ? basename(browserBinary) : browser)
  .toLowerCase().replace(/[^a-z0-9_-]/g, "_");
const devProfile = join(
  dirname(fileURLToPath(import.meta.url)), ".dev-profiles", profileKey,
);
mkdirSync(devProfile, { recursive: true });

export default defineConfig({
  plugins: [
    react(),
    webExtension({
      manifest: "manifest.json",
      browser,
      // The offscreen document is Chrome-only; Firefox runs capture in the
      // background event page (see src/shared/capture.ts).
      additionalInputs: [
        ...(browser === "chrome" ? ["src/offscreen/offscreen.html"] : []),
      ],
      watchFilePaths: ["manifest.json"],
      webExtConfig: {
        keepProfileChanges: true,
        profileCreateIfMissing: true,
        ...(browser === "firefox"
          ? {
              firefoxProfile: devProfile,
              ...(browserBinary ? { firefox: browserBinary } : {}),
              // Firefox blocks plain ws:// from extension pages as mixed
              // content even for loopback, which kills the local-dev training
              // WebSocket (ws://127.0.0.1:8000). Dev-profile-only override;
              // production uses wss:// and is unaffected.
              pref: { "network.websocket.allowInsecureFromHTTPS": true },
            }
          : { chromiumProfile: devProfile, ...(browserBinary ? { chromiumBinary: browserBinary } : {}) }),
      },
    }),
  ],
  // Build-time constant so the Chrome background tree-shakes the Firefox-only
  // direct-capture path (and its tesseract.js import) out of the service worker.
  define: {
    __BROWSER__: JSON.stringify(browser),
    __DEV_BUILD__: JSON.stringify(process.env.DEV_BUILD === "1"),
  },
  build: {
    outDir: `dist/${browser}`,
    emptyOutDir: true,
  },
});
