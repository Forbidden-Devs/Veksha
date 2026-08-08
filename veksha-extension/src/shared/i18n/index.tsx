import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { storageGet, storageSet } from "../platform";
import { catalogFor } from "./catalogs";
import { normalizeUiLocale } from "./locales";
import { EN, type Strings } from "./strings";

export const UI_LOCALE_STORAGE_KEY = "vk_i18n_current";

function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return normalizeUiLocale(raw);
}

export function loadStaticCatalog(language: string): Promise<Strings> {
  return Promise.resolve(catalogFor(normalizeUiLocale(language)));
}

interface I18nCtx {
  t: Strings;
  lang: string;
  previewLanguage: (lang: string) => void;
  switchLanguage: (lang: string) => Promise<void>;
}

const I18nContext = createContext<I18nCtx | null>(null);

function currentI18n(): I18nCtx {
  const context = useContext(I18nContext);
  if (!context) throw new Error("I18nProvider is missing");
  return context;
}

export function useT(): Strings {
  return currentI18n().t;
}

export function useI18n(): I18nCtx {
  return currentI18n();
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState("en");
  const [t, setT] = useState<Strings>(EN);
  const hasLocalSelection = useRef(false);

  const previewLanguage = useCallback((next: string): void => {
    const selected = normalizeUiLocale(next);
    hasLocalSelection.current = true;
    setLang(selected);
    setT(catalogFor(selected));
  }, []);

  useEffect(() => {
    void storageGet([UI_LOCALE_STORAGE_KEY]).then((values) => {
      if (hasLocalSelection.current) return;
      const selected = normalizeUiLocale(String(values[UI_LOCALE_STORAGE_KEY] ?? detectBrowserLang()));
      setLang(selected);
      setT(catalogFor(selected));
    });
  }, []);

  const switchLanguage = useCallback(async (next: string): Promise<void> => {
    const selected = normalizeUiLocale(next);
    await storageSet({ [UI_LOCALE_STORAGE_KEY]: selected });
    previewLanguage(selected);
  }, [previewLanguage]);

  const context = useMemo<I18nCtx>(
    () => ({ t, lang, previewLanguage, switchLanguage }),
    [lang, previewLanguage, switchLanguage, t],
  );

  return (
    <I18nContext.Provider value={context}>{children}</I18nContext.Provider>
  );
}
