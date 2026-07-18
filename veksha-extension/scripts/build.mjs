/**
 * build.mjs <browser> [--watch] [--binary <path>] — run the Vite build for a
 * browser target.
 *
 * Sets TARGET_BROWSER (and BROWSER_BINARY from --binary) for vite.config.ts.
 * A plain `VAR=x vite build` in npm scripts wouldn't work on Windows (same
 * reason sync-assets.mjs exists). --binary points web-ext at a specific
 * browser executable (Brave, Zen, …) for the auto-launch in watch mode.
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const [browser = "chrome", ...rest] = process.argv.slice(2);

const viteArgs = [];
let binary = process.env.BROWSER_BINARY;
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--binary") binary = rest[++i];
  else viteArgs.push(rest[i]);
}
const devBuild = viteArgs.includes("--watch");

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

function sanitizeTesseractRuntime() {
  const outputDir = join(root, "dist", browser);
  if (!existsSync(outputDir)) return;
  for (const path of walk(outputDir).filter((file) => file.endsWith(".js"))) {
    const code = readFileSync(path, "utf8");
    const sanitized = code.replace(
      /Function\("r","regeneratorRuntime = r"\)\(([A-Za-z_$][\w$]*)\)/g,
      "globalThis.regeneratorRuntime=$1",
    );
    if (sanitized !== code) writeFileSync(path, sanitized);
  }
}

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
if (result.status === 0 && !devBuild) sanitizeTesseractRuntime();
process.exit(result.status ?? 1);
