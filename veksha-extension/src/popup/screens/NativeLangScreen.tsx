import { useEffect, useRef, useState } from "react";
import { useI18n, useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";

const LANG_OPTIONS = LANGUAGES.filter((l) => l.code !== "auto");

function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANG_OPTIONS.some((l) => l.code === raw) ? raw : "en";
}

export function NativeLangScreen({ initialLang, onContinue }: { initialLang?: string; onContinue: (lang: string) => Promise<void> }) {
  const t = useT();
  const { lang, translating, switchLanguage } = useI18n();
  const [selected, setSelected] = useState<string>(() => initialLang ?? detectBrowserLang());
  const [query, setQuery] = useState("");
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

  const busy = loading || translating;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleLanguages = normalizedQuery
    ? LANG_OPTIONS.filter((language) =>
        language.name.toLocaleLowerCase().includes(normalizedQuery)
        || language.code.includes(normalizedQuery)
      )
    : LANG_OPTIONS;

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
    <section className="screen screen-lang-pick">
      <div className="lang-pick-header">
        <div className="logo-badge">Ve</div>
        <h1 className="lang-pick-title">{t.native_lang_title}</h1>
        <p className="lang-pick-subtitle">{t.native_lang_subtitle}</p>
      </div>

      <input
        className="text-input lang-pick-search"
        type="search"
        value={query}
        placeholder={t.settings_native_lang}
        aria-label={t.settings_native_lang}
        onChange={(event) => setQuery(event.target.value)}
      />

      <div className="lang-pick-grid">
        {visibleLanguages.map((lang) => (
          <button
            key={lang.code}
            className={`lang-card${selected === lang.code ? " lang-card--selected" : ""}`}
            aria-pressed={selected === lang.code}
            onClick={() => pick(lang.code)}
            type="button"
          >
            <span className="lang-card-name">{lang.name}</span>
          </button>
        ))}
        {visibleLanguages.length === 0 && (
          <p className="lang-pick-empty">{t.language_search_no_results}</p>
        )}
      </div>

      <div className="lang-pick-footer">
        <button
          className="btn btn-gradient btn-block"
          onClick={handleContinue}
          disabled={busy}
          type="button"
        >
          {busy ? t.app_loading : t.onboarding_continue}
        </button>
      </div>
    </section>
  );
}
