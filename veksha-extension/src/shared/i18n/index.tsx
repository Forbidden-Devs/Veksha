import { createContext, useContext, useEffect, useRef, useState } from "react";
import { CONFIG } from "../config";
import { LANGUAGES } from "../languages";
import { storageGet, storageSet } from "../platform";
import { EN, type Strings } from "./strings";

const CACHE_PREFIX = "vk_i18n_";
const CURRENT_LANG_KEY = "vk_i18n_current";

/** Browser UI language if we support it, otherwise "en". Used on first launch
 *  only — before the user has ever chosen a language explicitly. */
function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANGUAGES.some((l) => l.code === raw) ? raw : "en";
}

/** A cached catalogue: strings plus the convergence marker — keys whose
 *  correct translation IS the English text (mirrors the server-side
 *  `__same_as_en__` convention). Without the marker such keys would look
 *  "still untranslated" and be re-sent to the LLM on every load. */
type Catalog = Strings & { __same_as_en__?: string[] };

function untranslatedKeys(cached: Catalog): (keyof Strings)[] {
  const confirmed = new Set(cached.__same_as_en__ ?? []);
  return (Object.keys(EN) as (keyof Strings)[]).filter((k) => {
    if (confirmed.has(k)) return false;
    const value = cached[k];
    return typeof value !== "string" || !value.trim() || value.trim() === EN[k].trim();
  });
}

/** Translate fields that are missing, empty, or still contain the English source. */
async function fillMissingKeys(
  lang: string,
  cacheKey: string,
  cached: Catalog
): Promise<Strings> {
  const missing = untranslatedKeys(cached);
  if (missing.length === 0) return { ...EN, ...cached };

  const missingStrings = Object.fromEntries(missing.map((k) => [k, EN[k]]));
  try {
    const res = await fetch(`${CONFIG.BACKEND_URL}/api/i18n/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang, strings: missingStrings }),
    });
    if (res.ok) {
      const extra = (await res.json()) as Partial<Strings>;
      // Record keys the LLM translated to the English text verbatim, so they
      // are never asked about again.
      const confirmed = new Set(cached.__same_as_en__ ?? []);
      for (const [k, v] of Object.entries(extra)) {
        const source = EN[k as keyof Strings];
        if (typeof v === "string" && source && v.trim() === source.trim()) confirmed.add(k);
      }
      const merged: Catalog = { ...EN, ...cached, ...extra, __same_as_en__: [...confirmed] };
      storageSet({ [cacheKey]: merged });
      return merged;
    }
  } catch { /* ignore */ }

  // Fallback: EN values for missing keys
  return { ...EN, ...cached } as Strings;
}

async function doLoad(lang: string): Promise<Strings> {
  const cacheKey = `${CACHE_PREFIX}${lang}`;

  // 1. Local cache (chrome.storage.local, or localStorage on web)
  try {
    const stored = await storageGet([cacheKey]);
    if (stored[cacheKey]) {
      const cached = stored[cacheKey] as Catalog;
      return await fillMissingKeys(lang, cacheKey, cached);
    }
  } catch { /* ignore */ }

  // 2. Server cache
  try {
    const res = await fetch(`${CONFIG.BACKEND_URL}/api/i18n/${lang}`);
    if (res.ok) {
      const data = (await res.json()) as Catalog;
      // fillMissingKeys persists when it merges; persist the plain catalogue
      // here in case nothing was missing.
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

// One load per language per session: hopping between tiles on the language
// picker (or revisiting a language) reuses the same promise instead of
// re-fetching — and never fires a second LLM generation while the first one
// for the same language is still in flight.
const sessionLoads = new Map<string, Promise<Strings>>();

export function loadOrGenerateTranslation(lang: string): Promise<Strings> {
  if (!lang || lang === "en") return Promise.resolve(EN);

  const inFlight = sessionLoads.get(lang);
  if (inFlight) return inFlight;

  const load = doLoad(lang).then(
    (result) => {
      // Total failure fell back to bare EN — drop the memo so a later click
      // retries (e.g. the backend was briefly unreachable).
      if (result === EN) sessionLoads.delete(lang);
      return result;
    },
    (err) => {
      sessionLoads.delete(lang);
      throw err;
    },
  );
  sessionLoads.set(lang, load);
  return load;
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
  // The language picker switches on every tile click — when the user hops
  // between tiles, a slow older load must not overwrite the newest choice.
  const switchSeqRef = useRef(0);

  useEffect(() => {
    storageGet([CURRENT_LANG_KEY]).then((res) => {
      const stored = res[CURRENT_LANG_KEY] as string | undefined;
      // First launch (nothing stored yet): greet in the browser's language —
      // the same one the native-language picker preselects. Not persisted, so
      // the user's explicit choice at onboarding stays the source of truth.
      const lang = stored ?? detectBrowserLang();
      setLang(lang);
      if (lang && lang !== "en") {
        loadOrGenerateTranslation(lang).then(setT).catch(() => {});
      }
    });
  }, []);

  async function switchLanguage(next: string) {
    const seq = ++switchSeqRef.current;
    setTranslating(true);
    try {
      const strings = await loadOrGenerateTranslation(next);
      if (seq !== switchSeqRef.current) return; // superseded by a newer switch
      setT(strings);
      setLang(next || "en");
      storageSet({ [CURRENT_LANG_KEY]: next || "en" });
    } finally {
      if (seq === switchSeqRef.current) setTranslating(false);
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
      // Replace the session memo — later switches must see the fresh catalogue.
      sessionLoads.set(lang, Promise.resolve(merged));
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
