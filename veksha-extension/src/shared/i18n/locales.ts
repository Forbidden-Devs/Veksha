import policy from "./ui_locales.json";

export const UI_LOCALES = policy.required as readonly string[];
export const BETA_UI_LOCALES = policy.beta as readonly string[];

export function normalizeUiLocale(language: string | null | undefined): string {
  const code = String(language || "en").slice(0, 2).toLowerCase();
  return UI_LOCALES.includes(code) ? code : "en";
}
