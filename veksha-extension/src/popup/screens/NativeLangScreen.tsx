import { useEffect, useRef, useState } from "react";
import { useI18n, useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { LanguagePicker } from "../components/LanguagePicker";

const LANG_OPTIONS = LANGUAGES.filter((l) => l.code !== "auto");

function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANG_OPTIONS.some((l) => l.code === raw) ? raw : "en";
}

export function NativeLangScreen({ initialLang, onContinue }: { initialLang?: string; onContinue: (lang: string) => Promise<void> }) {
  const t = useT();
  const { lang, switchLanguage } = useI18n();
  const [selected, setSelected] = useState<string>(() => initialLang ?? detectBrowserLang());
  const [loading, setLoading] = useState(false);
  // Once the user has clicked a tile, their choice owns the selection.
  const touchedRef = useRef(false);

  // Until then, keep the preselected tile in sync with the interface language
  // (the provider resolves it async from storage / browser detection).
  useEffect(() => {
    if (!touchedRef.current && lang && LANG_OPTIONS.some((l) => l.code === lang)) {
      setSelected(lang);
    }
  }, [lang]);

  /** Tile click: select AND switch the surrounding interface right away,
   *  so the screen itself greets the user in the language they just chose. */
  function pick(code: string) {
    touchedRef.current = true;
    setSelected(code);
    switchLanguage(code).catch(() => {});
  }

  async function handleContinue() {
    setLoading(true);
    await onContinue(selected);
    // component unmounts after this so no setLoading(false) needed
  }

  return (
    <LanguagePicker
      title={t.native_lang_title}
      subtitle={t.native_lang_subtitle}
      searchLabel={t.settings_native_lang}
      emptyLabel={t.language_search_no_results}
      options={LANG_OPTIONS}
      selectedCodes={new Set([selected])}
      onSelect={pick}
      footer={
        <button
          className="btn btn-gradient btn-block"
          onClick={handleContinue}
          disabled={loading}
          type="button"
        >
          {loading ? t.app_loading : t.onboarding_continue}
        </button>
      }
    />
  );
}
