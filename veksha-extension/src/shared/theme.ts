/**
 * theme.ts — runtime palette switching.
 *
 * Themes are CSS-token sets in popup/theme.css keyed by the
 * `data-veksha-theme` attribute on <html>. The chosen name persists in
 * storage (vk_theme) and is shared by every surface: popup, training/lesson
 * pages, the web app, and the content-script overlays (which read the same
 * key and tag their own overlay roots).
 */
import { storageGet, storageSet } from "./platform";

export const THEMES = ["light", "dark"] as const;
export type ThemeName = (typeof THEMES)[number];

export const THEME_STORAGE_KEY = "vk_theme";
const DEFAULT_THEME: ThemeName = "light";

export async function getTheme(): Promise<ThemeName> {
  try {
    const st = await storageGet([THEME_STORAGE_KEY]);
    const name = st[THEME_STORAGE_KEY] as string | undefined;
    if (THEMES.includes(name as ThemeName)) return name as ThemeName;
    // Migrate the four experimental palettes to the unified light/dark pair.
    if (name === "dusk" || name === "hazel" || name === "midnight") return "dark";
    if (name === "lavender") return "light";
    return DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

function applyAttr(name: ThemeName): void {
  document.documentElement.dataset.vekshaTheme = name;
}

/** Apply the stored theme; call once at every entry point before render. */
export async function initTheme(): Promise<void> {
  applyAttr(await getTheme());
}

export async function setTheme(name: ThemeName): Promise<void> {
  applyAttr(name);
  await storageSet({ [THEME_STORAGE_KEY]: name });
}
