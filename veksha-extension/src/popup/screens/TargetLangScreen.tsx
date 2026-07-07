import { useState } from "react";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";

export function TargetLangScreen({
  nativeLang,
  onContinue,
}: {
  nativeLang: string;
  onContinue: (lang: string) => Promise<void>;
}) {
  const t = useT();
  const options = LANGUAGES.filter((l) => l.code !== "auto" && l.code !== nativeLang);
  const [selected, setSelected] = useState<string>(options[0]?.code ?? "en");
  const [loading, setLoading] = useState(false);

  async function handleContinue() {
    setLoading(true);
    try {
      await onContinue(selected);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="screen screen-lang-pick">
      <div className="lang-pick-header">
        <div className="logo-badge">Ve</div>
        <h1 className="lang-pick-title">{t.target_lang_title}</h1>
        <p className="lang-pick-subtitle">{t.target_lang_subtitle}</p>
      </div>

      <div className="lang-pick-grid">
        {options.map((lang) => (
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
          disabled={loading}
          type="button"
        >
          {loading ? t.onboarding_loading : t.target_lang_start}
        </button>
      </div>
    </section>
  );
}
