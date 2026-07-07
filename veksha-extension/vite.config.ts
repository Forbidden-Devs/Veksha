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
        "src/permission/permission.html",
      ],
      watchFilePaths: ["manifest.json"],
      webExtConfig: browserBinary
        ? (browser === "firefox" ? { firefox: browserBinary } : { chromiumBinary: browserBinary })
        : undefined,
    }),
  ],
  // Build-time constant so the Chrome background tree-shakes the Firefox-only
  // direct-capture path (and its tesseract.js import) out of the service worker.
  define: {
    __BROWSER__: JSON.stringify(browser),
  },
  build: {
    outDir: `dist/${browser}`,
    emptyOutDir: true,
  },
});
