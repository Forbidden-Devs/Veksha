import { createContext, useContext, useEffect, useState } from "react";
import { CONFIG } from "../config";
import { storageGet, storageSet } from "../platform";
import { EN, type Strings } from "./strings";

const CACHE_PREFIX = "vk_i18n_";
const CURRENT_LANG_KEY = "vk_i18n_current";

/** Translate fields that are missing, empty, or still contain the English source. */
async function fillMissingKeys(
  lang: string,
  cacheKey: string,
  cached: Strings
): Promise<Strings> {
  const missing = (Object.keys(EN) as (keyof Strings)[]).filter((k) => {
    const value = cached[k];
    return typeof value !== "string" || !value.trim() || value.trim() === EN[k].trim();
  });
  if (missing.length === 0) return cached;

  const missingStrings = Object.fromEntries(missing.map((k) => [k, EN[k]]));
  try {
    const res = await fetch(`${CONFIG.BACKEND_URL}/api/i18n/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang, strings: missingStrings }),
    });
    if (res.ok) {
      const extra = (await res.json()) as Partial<Strings>;
      const merged = { ...EN, ...cached, ...extra } as Strings;
      storageSet({ [cacheKey]: merged });
      return merged;
    }
  } catch { /* ignore */ }

  // Fallback: EN values for missing keys
  return { ...EN, ...cached } as Strings;
}

export async function loadOrGenerateTranslation(lang: string): Promise<Strings> {
  if (!lang || lang === "en") return EN;

  const cacheKey = `${CACHE_PREFIX}${lang}`;

  // 1. Local cache (chrome.storage.local, or localStorage on web)
  try {
    const stored = await storageGet([cacheKey]);
    if (stored[cacheKey]) {
      const cached = stored[cacheKey] as Strings;
      return await fillMissingKeys(lang, cacheKey, cached);
    }
  } catch { /* ignore */ }

  // 2. Server cache
  try {
    const res = await fetch(`${CONFIG.BACKEND_URL}/api/i18n/${lang}`);
    if (res.ok) {
      const data = (await res.json()) as Strings;
      const filled = await fillMissingKeys(lang, cacheKey, data);
      storageSet({ [cacheKey]: filled });
      return filled;
    }
  } catch { /* ignore */ }

  // 3. LLM generate (full translation)
  try {
    const res = await fetch(`${CONFIG.BACKEND_URL}/api/i18n/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang }),
    });
    if (res.ok) {
      const data = (await res.json()) as Strings;
      storageSet({ [cacheKey]: data });
      return data;
    }
  } catch { /* ignore */ }

  return EN;
}

interface I18nCtx {
  t: Strings;
  lang: string;
  switchLanguage: (lang: string) => Promise<void>;
  regenerate: () => Promise<string>;
  translating: boolean;
}

const I18nContext = createContext<I18nCtx>({
  t: EN,
  lang: "en",
  switchLanguage: async () => {},
  regenerate: async () => "en",
  translating: false,
});

export function useT(): Strings {
  return useContext(I18nContext).t;
}

export function useI18n(): I18nCtx {
  return useContext(I18nContext);
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [t, setT] = useState<Strings>(EN);
  const [lang, setLang] = useState("en");
  const [translating, setTranslating] = useState(false);

  useEffect(() => {
    storageGet([CURRENT_LANG_KEY]).then((res) => {
      const stored = (res[CURRENT_LANG_KEY] as string | undefined) ?? "en";
      setLang(stored);
      if (stored && stored !== "en") {
        loadOrGenerateTranslation(stored).then(setT).catch(() => {});
      }
    });
  }, []);

  async function switchLanguage(next: string) {
    setTranslating(true);
    try {
      const strings = await loadOrGenerateTranslation(next);
      setT(strings);
      setLang(next || "en");
      storageSet({ [CURRENT_LANG_KEY]: next || "en" });
    } finally {
      setTranslating(false);
    }
  }

  /** Force a full re-translation of the current language from the live EN
   *  source — bypasses the cache (which keeps stale strings whenever UI text
   *  changes but the key name stays the same). */
  async function regenerate(): Promise<string> {
    if (!lang || lang === "en") return lang;
    setTranslating(true);
    try {
      const res = await fetch(`${CONFIG.BACKEND_URL}/api/i18n/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang, strings: EN }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const extra = (await res.json()) as Partial<Strings>;
      const merged = { ...EN, ...extra } as Strings;
      await storageSet({ [`${CACHE_PREFIX}${lang}`]: merged });
      setT(merged);
      return lang;
    } finally {
      setTranslating(false);
    }
  }

  return (
    <I18nContext.Provider value={{ t, lang, switchLanguage, regenerate, translating }}>
      {children}
    </I18nContext.Provider>
  );
}
