import { useState } from "react";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";

interface LevelSetupResult {
  level: string;
  goals: string;
  prompt: string;
}

export function LevelSetupScreen({
  initialValues,
  targetLang,
  onComplete,
  onBack,
}: {
  initialValues?: LevelSetupResult;
  targetLang: string;
  onComplete: (opts: LevelSetupResult) => Promise<void>;
  onBack: () => void;
}) {
  const t = useT();
  const [level, setLevel] = useState(initialValues?.level ?? "");
  const [goals, setGoals] = useState(initialValues?.goals ?? "");
  const [prompt, setPrompt] = useState(initialValues?.prompt ?? "");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const targetName = LANGUAGES.find((language) => language.code === targetLang)?.name ?? targetLang.toUpperCase();

  // CEFR grade scale (labels are universal codes — no translation needed).
  const LEVELS = [
    { value: "a1", label: "A1" },
    { value: "a1_a2", label: "A1/A2" },
    { value: "a2", label: "A2" },
    { value: "a2_b1", label: "A2/B1" },
    { value: "b1", label: "B1" },
    { value: "b1_b2", label: "B1/B2" },
    { value: "b2", label: "B2" },
    { value: "b2_c1", label: "B2/C1" },
    { value: "c1", label: "C1" },
    { value: "c1_c2", label: "C1/C2" },
    { value: "c2", label: "C2" },
  ];

  async function handleContinue() {
    if (!level) { setError(t.settings_err_no_level); return; }
    setError(null);
    setLoading(true);
    try {
      await onComplete({ level, goals, prompt });
    } catch (err) {
      // Keep the user on the final onboarding step instead of opening a
      // partially configured profile with missing/incorrect languages.
      setError(`${t.settings_err_save}: ${(err as Error).message}`);
      setLoading(false);
    }
  }

  return (
    <section className="screen screen-settings">
      <div className="lang-pick-header">
        <button className="onboarding-back" type="button" onClick={onBack} disabled={loading}>
          <span aria-hidden="true">←</span> {t.tutorial_back}
        </button>
        <div className="logo-badge">Ve</div>
        <h1 className="lang-pick-title">{t.level_setup_title}</h1>
        <div className="lang-code">{targetName}</div>
        <p className="lang-pick-subtitle">{t.level_setup_subtitle}</p>
      </div>

      <div className="settings-body">
        <label className="field-label" htmlFor="ls-level">{t.settings_level}</label>
        <select
          id="ls-level"
          className="select-input"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option value="" disabled>{t.settings_level_placeholder}</option>
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </select>

        <label className="field-label" htmlFor="ls-goals">
          {t.settings_goals} <span className="optional-tag">({t.level_setup_optional})</span>
        </label>
        <textarea
          id="ls-goals"
          className="textarea-input"
          rows={2}
          placeholder={t.settings_goals_placeholder}
          value={goals}
          onChange={(e) => setGoals(e.target.value)}
        />

        <label className="field-label" htmlFor="ls-prompt">
          {t.settings_prompt_label} <span className="optional-tag">({t.level_setup_optional})</span>
        </label>
        <textarea
          id="ls-prompt"
          className="textarea-input"
          rows={2}
          placeholder={t.settings_prompt_placeholder}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        {error && <p className="onboarding-error">{error}</p>}
      </div>

      <div className="settings-footer">
        <button
          className="btn btn-gradient btn-block"
          disabled={loading}
          onClick={handleContinue}
          type="button"
        >
          {loading ? t.app_loading : t.target_lang_start}
        </button>
      </div>
    </section>
  );
}
