/**
 * sync-assets.mjs — copy static assets into public/ before the Vite build.
 * Cross-platform replacement for the original PowerShell script.
 *
 * Copies:
 *   source/*                          -> public/source/
 *   icons/icon{16,48,128}.png         -> public/icons/
 */
import {
  cpSync,
  copyFileSync,
  mkdirSync,
  rmSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { syncI18n } from "./sync-i18n.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
syncI18n();

const sourceDir = join(root, "source");
// Recreate the generated dirs from scratch so files deleted from source/
// don't linger in public/ (and end up shipped in dist/).
const publicSource = join(root, "public", "source");
rmSync(publicSource, { recursive: true, force: true });
mkdirSync(publicSource, { recursive: true });
cpSync(sourceDir, publicSource, { recursive: true });

const publicIcons = join(root, "public", "icons");
rmSync(publicIcons, { recursive: true, force: true });
mkdirSync(publicIcons, { recursive: true });
for (const name of ["icon16.png", "icon48.png", "icon128.png"]) {
  copyFileSync(join(root, "icons", name), join(publicIcons, name));
}

console.log("[sync-assets] done");
