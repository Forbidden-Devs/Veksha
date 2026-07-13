/**
 * Build and package deterministic store upload archives for Chrome and
 * Firefox, plus the readable source archive required by AMO reviewers.
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const artifactsDir = join(root, "artifacts");
const packageJson = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const version = packageJson.version;

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status ?? "unknown"}`);
  }
}

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

function validateTarget(browser) {
  const distDir = join(root, "dist", browser);
  const manifestPath = join(distDir, "manifest.json");
  if (!existsSync(manifestPath)) throw new Error(`Missing ${manifestPath}`);

  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (manifest.version !== version) {
    throw new Error(`${browser}: manifest version ${manifest.version} does not match package version ${version}`);
  }
  if (manifest.host_permissions?.some((origin) => /localhost|127\.0\.0\.1/.test(origin))) {
    throw new Error(`${browser}: release manifest contains a local development origin`);
  }
  const invalidHostPattern = manifest.host_permissions?.find(
    (origin) => origin !== "<all_urls>" && !/^(https?|file):\/\//.test(origin),
  );
  if (invalidHostPattern) {
    throw new Error(`${browser}: invalid host permission match pattern: ${invalidHostPattern}`);
  }
  if (browser === "chrome") {
    if (!manifest.background?.service_worker) throw new Error("Chrome package has no service worker");
    if (manifest.browser_specific_settings) throw new Error("Chrome package contains Firefox settings");
  } else {
    const gecko = manifest.browser_specific_settings?.gecko;
    if (!manifest.background?.scripts) throw new Error("Firefox package has no background scripts");
    if (!gecko?.id) throw new Error("Firefox package has no explicit Gecko ID");
    if (!gecko?.data_collection_permissions) {
      throw new Error("Firefox package has no data collection declaration");
    }
    if (manifest.permissions?.includes("offscreen")) {
      throw new Error("Firefox package contains the Chrome-only offscreen permission");
    }
  }

  const sourceMaps = walk(distDir).filter((path) => path.endsWith(".map"));
  if (sourceMaps.length) throw new Error(`${browser}: source maps found in release output`);
  return distDir;
}

function zipDirectory(sourceDir, destination) {
  rmSync(destination, { force: true });
  run("zip", ["-q", "-r", destination, "."], { cwd: sourceDir });
  run("unzip", ["-tq", destination]);
}

function zipSources(destination) {
  const inputs = [
    "AMO_SOURCE_README.md",
    "README.md",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "vite.config.ts",
    "manifest.json",
    "icons",
    "scripts",
    "source",
    "src",
  ];
  for (const input of inputs) {
    if (!existsSync(join(root, input))) throw new Error(`Missing source input: ${input}`);
  }
  rmSync(destination, { force: true });
  run("zip", ["-q", "-r", destination, ...inputs, "-x", "*.DS_Store"]);
  run("unzip", ["-tq", destination]);
}

rmSync(artifactsDir, { recursive: true, force: true });
mkdirSync(artifactsDir, { recursive: true });
// Invoke the project scripts with the current Node binary so packaging also
// works in hermetic environments where Node is present but `npm` is not on
// PATH. Dependencies must already have been installed (`npm ci`).
run(process.execPath, ["scripts/sync-assets.mjs"]);
run(process.execPath, ["scripts/build.mjs", "chrome"]);
run(process.execPath, ["scripts/sync-assets.mjs"]);
run(process.execPath, ["scripts/build.mjs", "firefox"]);

const chromeDir = validateTarget("chrome");
const firefoxDir = validateTarget("firefox");
const chromeZip = resolve(artifactsDir, `veksha-${version}-chrome.zip`);
const firefoxZip = resolve(artifactsDir, `veksha-${version}-firefox.zip`);
const sourcesZip = resolve(artifactsDir, `veksha-${version}-firefox-sources.zip`);

zipDirectory(chromeDir, chromeZip);
zipDirectory(firefoxDir, firefoxZip);
zipSources(sourcesZip);

for (const path of [chromeZip, firefoxZip, sourcesZip]) {
  console.log(`${path} (${(statSync(path).size / 1024 / 1024).toFixed(2)} MiB)`);
}
