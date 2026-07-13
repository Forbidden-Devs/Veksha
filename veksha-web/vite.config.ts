import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// The web app reuses the extension popup source tree directly (see src/main.tsx
// importing from ../veksha-extension/src). fs.allow lets the dev server read
// files outside the project root.
export default defineConfig({
  plugins: [react()],
  define: {
    // The web app never ships debug tooling; the extension sets this per build.
    __DEV_BUILD__: JSON.stringify(false),
  },
  server: {
    fs: { allow: [path.resolve(__dirname, "..")] },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
