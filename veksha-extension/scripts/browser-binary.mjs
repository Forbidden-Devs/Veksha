/**
 * browser-binary.mjs — locate the executable of a dev browser (Brave, Zen, …)
 * on the current OS.
 *
 * The npm dev scripts must not hardcode a path: `dev:brave` has to work on
 * macOS, Linux, and Windows alike. Lookup order per browser:
 *   1. explicit env override (BRAVE_BINARY / ZEN_BINARY, or BROWSER_BINARY)
 *   2. an executable of that name on PATH
 *   3. the usual install locations of the current platform
 * Nothing found → null; the caller falls back to the stock browser of the
 * same family (web-ext's default) so `npm run dev` still starts.
 */
import { accessSync, constants } from "node:fs";
import { delimiter, isAbsolute, join } from "node:path";
import { homedir } from "node:os";

const { env, platform } = process;

/** %VAR%-style Windows dirs, skipped when the variable is unset. */
const winDirs = [
  env.PROGRAMFILES,
  env["ProgramFiles(x86)"],
  env.LOCALAPPDATA,
].filter(Boolean);

export const BROWSERS = {
  brave: {
    envVar: "BRAVE_BINARY",
    commands: ["brave", "brave-browser", "brave-browser-stable"],
    paths: {
      darwin: [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "~/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
      ],
      linux: [
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
        "/opt/brave.com/brave/brave-browser",
        "/snap/bin/brave",
        "/var/lib/flatpak/exports/bin/com.brave.Browser",
        "~/.local/share/flatpak/exports/bin/com.brave.Browser",
      ],
      win32: winDirs.map((dir) =>
        join(dir, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
      ),
    },
  },
  zen: {
    envVar: "ZEN_BINARY",
    commands: ["zen", "zen-browser"],
    paths: {
      darwin: [
        "/Applications/Zen.app/Contents/MacOS/zen",
        "/Applications/Zen Browser.app/Contents/MacOS/zen",
        "~/Applications/Zen.app/Contents/MacOS/zen",
      ],
      linux: [
        "/usr/bin/zen-browser",
        "/usr/bin/zen",
        "/opt/zen-browser-bin/zen",
        "/opt/zen/zen",
        "/var/lib/flatpak/exports/bin/app.zen_browser.zen",
        "~/.local/share/flatpak/exports/bin/app.zen_browser.zen",
      ],
      win32: winDirs.map((dir) => join(dir, "Zen Browser", "zen.exe")),
    },
  },
};

const expandHome = (p) =>
  p.startsWith("~/") ? join(homedir(), p.slice(2)) : p;

const isExecutable = (p) => {
  try {
    // X_OK is meaningless on Windows; existence is the only usable check.
    accessSync(p, platform === "win32" ? constants.F_OK : constants.X_OK);
    return true;
  } catch {
    return false;
  }
};

/** `which`, without shelling out. */
function onPath(command) {
  const exts =
    platform === "win32"
      ? (env.PATHEXT ?? ".EXE;.CMD;.BAT").split(";").filter(Boolean)
      : [""];
  for (const dir of (env.PATH ?? "").split(delimiter).filter(Boolean)) {
    for (const ext of exts) {
      const candidate = join(dir, command + ext);
      if (isExecutable(candidate)) return candidate;
    }
  }
  return null;
}

/**
 * @param {keyof BROWSERS} name
 * @returns {string | null} absolute path to the executable, or null
 */
export function resolveBrowserBinary(name) {
  const browser = BROWSERS[name];
  if (!browser) throw new Error(`Unknown browser "${name}"`);

  const override = env[browser.envVar] || env.BROWSER_BINARY;
  // An override is the user's explicit choice: honour it as given, even if
  // it is a bare command name resolved through PATH.
  if (override) {
    if (isAbsolute(override)) return override;
    return onPath(override) ?? override;
  }

  for (const command of browser.commands) {
    const found = onPath(command);
    if (found) return found;
  }
  for (const candidate of browser.paths[platform] ?? []) {
    const expanded = expandHome(candidate);
    if (isExecutable(expanded)) return expanded;
  }
  return null;
}
