import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { LANGUAGES } from "../languages";
import { storageGet, storageSet } from "../platform";
import { catalogFor } from "./catalogs";
import { EN, type Strings } from "./strings";

const CURRENT_LANG_KEY = "vk_i18n_current";

function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANGUAGES.some((language) => language.code === raw) ? raw : "en";
}

export function loadStaticCatalog(language: string): Promise<Strings> {
  return Promise.resolve(catalogFor(language || "en"));
}

interface I18nCtx {
  t: Strings;
  lang: string;
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

  useEffect(() => {
    void storageGet([CURRENT_LANG_KEY]).then((values) => {
      const selected = String(values[CURRENT_LANG_KEY] ?? detectBrowserLang());
      setLang(selected);
      setT(catalogFor(selected));
    });
  }, []);

  const switchLanguage = useCallback(async (next: string): Promise<void> => {
    const selected = next || "en";
    await storageSet({ [CURRENT_LANG_KEY]: selected });
    setLang(selected);
    setT(catalogFor(selected));
  }, []);

  const context = useMemo<I18nCtx>(() => ({ t, lang, switchLanguage }), [lang, switchLanguage, t]);

  return (
    <I18nContext.Provider value={context}>{children}</I18nContext.Provider>
  );
}
