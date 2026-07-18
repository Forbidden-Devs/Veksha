import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const files = {
  package: join(root, "package.json"),
  lock: join(root, "package-lock.json"),
  manifest: join(root, "manifest.json"),
};

const VERSION_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

export function parseVersion(value) {
  const match = VERSION_PATTERN.exec(value);
  if (!match) {
    throw new Error(`Invalid version "${value}". Expected X.Y.Z without prerelease data.`);
  }
  return match.slice(1).map(Number);
}

export function nextVersion(current, requested) {
  if (VERSION_PATTERN.test(requested)) {
    parseVersion(requested);
    return requested;
  }

  const [major, minor, patch] = parseVersion(current);
  if (requested === "major") return `${major + 1}.0.0`;
  if (requested === "minor") return `${major}.${minor + 1}.0`;
  if (requested === "patch") return `${major}.${minor}.${patch + 1}`;
  throw new Error(`Unknown bump "${requested}". Use patch, minor, major, or X.Y.Z.`);
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJson(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function loadVersions() {
  const packageJson = readJson(files.package);
  const packageLock = readJson(files.lock);
  const manifest = readJson(files.manifest);
  return { packageJson, packageLock, manifest };
}

export function checkVersions() {
  const { packageJson, packageLock, manifest } = loadVersions();
  const expected = packageJson.version;
  parseVersion(expected);

  const actual = {
    "package-lock.json": packageLock.version,
    "package-lock.json packages[\"\"]": packageLock.packages?.[""]?.version,
    "manifest.json": manifest.version,
  };
  const mismatches = Object.entries(actual).filter(([, version]) => version !== expected);
  if (mismatches.length) {
    const details = mismatches.map(([name, version]) => `${name}=${version ?? "missing"}`).join(", ");
    throw new Error(`Version mismatch: package.json=${expected}; ${details}`);
  }
  return expected;
}

export function setVersion(requested) {
  const { packageJson, packageLock, manifest } = loadVersions();
  const version = nextVersion(packageJson.version, requested);

  packageJson.version = version;
  packageLock.version = version;
  if (!packageLock.packages?.[""]) {
    throw new Error('package-lock.json has no packages[""] entry');
  }
  packageLock.packages[""].version = version;
  manifest.version = version;

  writeJson(files.package, packageJson);
  writeJson(files.lock, packageLock);
  writeJson(files.manifest, manifest);
  return version;
}

function main(args) {
  if (args.length === 1 && args[0] === "--check") return checkVersions();
  if (args.length === 2 && args[0] === "--dry-run") {
    return nextVersion(checkVersions(), args[1]);
  }
  if (args.length === 1) return setVersion(args[0]);
  throw new Error("Usage: node scripts/set-version.mjs [--check | --dry-run <bump> | <bump>] ");
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log(main(process.argv.slice(2)));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
