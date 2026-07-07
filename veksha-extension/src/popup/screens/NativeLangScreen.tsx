import { useState } from "react";
import { useI18n, useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";

const LANG_OPTIONS = LANGUAGES.filter((l) => l.code !== "auto");

function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANG_OPTIONS.some((l) => l.code === raw) ? raw : "en";
}

export function NativeLangScreen({ onContinue }: { onContinue: (lang: string) => Promise<void> }) {
  const t = useT();
  const { translating } = useI18n();
  const [selected, setSelected] = useState<string>(detectBrowserLang);
  const [loading, setLoading] = useState(false);

  const busy = loading || translating;

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

      <div className="lang-pick-grid">
        {LANG_OPTIONS.map((lang) => (
          <button
            key={lang.code}
            className={`lang-card${selected === lang.code ? " lang-card--selected" : ""}`}
            onClick={() => setSelected(lang.code)}
            type="button"
          >
            <span className="lang-code">{lang.code.toUpperCase()}</span>
            <span className="lang-card-name">{lang.name}</span>
          </button>
        ))}
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
