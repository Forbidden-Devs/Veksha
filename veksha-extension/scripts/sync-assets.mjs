/**
 * sync-assets.mjs — copy static assets into public/ before the Vite build.
 * Cross-platform replacement for the original PowerShell script.
 *
 * Copies:
 *   source/*                          -> public/source/
 *   icons/icon{16,48,128}.png         -> public/icons/
 *   tesseract.js worker + wasm cores  -> public/tesseract/
 *   source/tesseract-lang/*.gz        -> public/tesseract/lang/
 */
import {
  cpSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

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

// --- Tesseract.js OCR assets (worker + wasm core + language models) ---
const tessPublic = join(root, "public", "tesseract");
const tessLangPublic = join(tessPublic, "lang");
rmSync(tessPublic, { recursive: true, force: true });
mkdirSync(tessLangPublic, { recursive: true });

const tessWorker = join(root, "node_modules", "tesseract.js", "dist", "worker.min.js");
if (existsSync(tessWorker)) {
  // Tesseract's prebuilt worker retains legacy eval-like fallbacks for browsers
  // without globalThis. Our supported browsers all provide globalThis, and AMO
  // rejects Function constructors even when that fallback is unreachable.
  const workerCode = readFileSync(tessWorker, "utf8")
    .replace(
      /Function\("r","regeneratorRuntime = r"\)\(([A-Za-z_$][\w$]*)\)/g,
      "globalThis.regeneratorRuntime=$1",
    )
    .replace(/new Function\("return this"\)\(\)/g, "globalThis");
  writeFileSync(join(tessPublic, "worker.min.js"), workerCode);
}

const tessCoreDir = join(root, "node_modules", "tesseract.js-core");
if (existsSync(tessCoreDir)) {
  for (const name of readdirSync(tessCoreDir)) {
    if (name.startsWith("tesseract-core")) {
      copyFileSync(join(tessCoreDir, name), join(tessPublic, name));
    }
  }
}

const tessLangSrc = join(sourceDir, "tesseract-lang");
if (existsSync(tessLangSrc)) {
  for (const name of readdirSync(tessLangSrc)) {
    if (name.endsWith(".traineddata.gz")) {
      copyFileSync(join(tessLangSrc, name), join(tessLangPublic, name));
    }
  }
}

console.log("[sync-assets] done");
