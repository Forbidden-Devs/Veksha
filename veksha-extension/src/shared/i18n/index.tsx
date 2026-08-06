import { createContext, useContext, useEffect, useState } from "react";
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
  const [lang, setLang] = useState("en");
  const [t, setT] = useState<Strings>(EN);

  useEffect(() => {
    void storageGet([CURRENT_LANG_KEY]).then((values) => {
      const selected = String(values[CURRENT_LANG_KEY] ?? detectBrowserLang());
      setLang(selected);
      setT(catalogFor(selected));
    });
  }, []);

  async function switchLanguage(next: string): Promise<void> {
    const selected = next || "en";
    await storageSet({ [CURRENT_LANG_KEY]: selected });
    setLang(selected);
    setT(catalogFor(selected));
  }

  return (
    <I18nContext.Provider value={{
      t,
      lang,
      switchLanguage,
      regenerate: async () => lang,
      translating: false,
    }}>
      {children}
    </I18nContext.Provider>
  );
}
