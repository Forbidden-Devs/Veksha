import { useState } from "react";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";

export function TargetLangScreen({
  nativeLang,
  initialLangs,
  onContinue,
  onBack,
}: {
  nativeLang: string;
  initialLangs?: string[];
  onContinue: (langs: string[]) => Promise<void>;
  onBack: () => void;
}) {
  const t = useT();
  const options = LANGUAGES.filter((l) => l.code !== "auto" && l.code !== nativeLang);
  const [selected, setSelected] = useState<string[]>(() => {
    return (initialLangs ?? []).filter((code) => options.some((l) => l.code === code));
  });
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
        <button className="onboarding-back" type="button" onClick={onBack} disabled={loading}>
          <span aria-hidden="true">←</span> {t.tutorial_back}
        </button>
        <div className="logo-badge">Ve</div>
        <h1 className="lang-pick-title">{t.target_lang_title}</h1>
        <p className="lang-pick-subtitle">{t.target_lang_subtitle}</p>
      </div>

      <div className="lang-pick-grid">
        {options.map((lang) => (
          <button
            key={lang.code}
            className={`lang-card${selected.includes(lang.code) ? " lang-card--selected" : ""}`}
            aria-pressed={selected.includes(lang.code)}
            onClick={() => setSelected((current) =>
              current.includes(lang.code)
                ? current.filter((code) => code !== lang.code)
                : [...current, lang.code]
            )}
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
          disabled={loading || selected.length === 0}
          type="button"
        >
          {loading ? t.onboarding_loading : t.target_lang_start}
        </button>
      </div>
    </section>
  );
}
