import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";


const extensionRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const repositoryRoot = dirname(extensionRoot);
const reviewedDir = join(repositoryRoot, "veksha-backend", "data");
const bundledDir = join(extensionRoot, "src", "shared", "i18n", "catalogs");
const policyTarget = join(extensionRoot, "src", "shared", "i18n", "ui_locales.json");

export function syncI18n() {
  // Standalone extension images use veksha-extension as their Docker context,
  // so the backend source tree is intentionally unavailable there. In that
  // case the already reviewed, tracked bundle is the build input.
  if (!existsSync(reviewedDir)) {
    if (!existsSync(bundledDir) || !existsSync(policyTarget)) {
      throw new Error("Bundled localization catalogues are missing");
    }
    return;
  }
  mkdirSync(bundledDir, { recursive: true });
  for (const name of readdirSync(reviewedDir)) {
    if (/^i18n_[a-z-]+\.json$/.test(name)) {
      copyFileSync(join(reviewedDir, name), join(bundledDir, name));
    }
  }
  copyFileSync(join(reviewedDir, "ui_locales.json"), policyTarget);
}
