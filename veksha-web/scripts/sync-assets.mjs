/**
 * sync-assets.mjs — copy shared assets from the extension tree into public/
 * before dev/build, so they are not duplicated in git.
 */
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const extSource = join(root, "..", "veksha-extension", "source");

const publicSource = join(root, "public", "source");
mkdirSync(publicSource, { recursive: true });
// Only what the study app actually references from the extension workspace.
copyFileSync(join(extSource, "back.png"), join(publicSource, "back.png"));

console.log("[sync-assets] done");
