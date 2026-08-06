/**
 * build.mjs <browser> [--watch] [--binary <path>] [--app <name>] — run the
 * Vite build for a browser target.
 *
 * Sets TARGET_BROWSER (and BROWSER_BINARY from --binary/--app) for
 * vite.config.ts. A plain `VAR=x vite build` in npm scripts wouldn't work on
 * Windows (same reason sync-assets.mjs exists). The binary points web-ext at
 * a specific browser executable for the auto-launch in watch mode: --binary
 * takes a literal path, --app takes a name (brave, zen) that is looked up per
 * platform, so the npm scripts stay OS-independent.
 */
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveBrowserBinary } from "./browser-binary.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const [browser = "chrome", ...rest] = process.argv.slice(2);

const viteArgs = [];
let binary = process.env.BROWSER_BINARY;
let app;
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--binary") binary = rest[++i];
  else if (rest[i] === "--app") app = rest[++i];
  else viteArgs.push(rest[i]);
}

if (!binary && app) {
  binary = resolveBrowserBinary(app);
  if (!binary) {
    console.warn(
      `[build] ${app} not found on this system — launching the default ` +
        `${browser === "firefox" ? "Firefox" : "Chrome"} instead. ` +
        `Set ${app.toUpperCase()}_BINARY=<path> to point at your install.`,
    );
  }
}
const devBuild = viteArgs.includes("--watch");

const result = spawnSync(
  process.execPath,
  [join(root, "node_modules", "vite", "bin", "vite.js"), "build", ...viteArgs],
  {
    stdio: "inherit",
    cwd: root,
    env: {
      ...process.env,
      TARGET_BROWSER: browser,
      DEV_BUILD: devBuild ? "1" : "0",
      ...(binary ? { BROWSER_BINARY: binary } : {}),
    },
  },
);
process.exit(result.status ?? 1);
