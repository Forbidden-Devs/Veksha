import { useState } from "react";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";

interface LevelSetupResult { level: string; goals: string; prompt: string }
const LEVELS = ["a1", "a1_a2", "a2", "a2_b1", "b1", "b1_b2", "b2", "b2_c1", "c1", "c1_c2", "c2"];

export function LevelSetupScreen({ initialValues, targetLang, onComplete, onBack }: {
  initialValues?: LevelSetupResult;
  targetLang: string;
  onComplete: (result: LevelSetupResult) => Promise<void>;
  onBack: () => void;
}) {
  const t = useT();
  const [form, setForm] = useState<LevelSetupResult>(initialValues ?? { level: "", goals: "", prompt: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const language = LANGUAGES.find((item) => item.code === targetLang)?.name ?? targetLang.toUpperCase();

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!form.level) return setError(t.settings_err_no_level);
    setBusy(true);
    setError("");
    try { await onComplete(form); }
    catch (reason) { setError(`${t.settings_err_save}: ${(reason as Error).message}`); setBusy(false); }
  }

  return (
    <section className="setup-surface" aria-labelledby="setup-level-title">
      <button className="setup-back" type="button" onClick={onBack} disabled={busy}>← {t.common_back}</button>
      <form className="setup-card setup-card-wide" onSubmit={(event) => void submit(event)}>
        <p className="setup-kicker">{language}</p>
        <h1 id="setup-level-title">{t.level_setup_title}</h1>
        <p>{t.level_setup_subtitle}</p>
        <label className="setup-field"><span>{t.settings_level}</span><select value={form.level} onChange={(event) => setForm({ ...form, level: event.target.value })}><option value="">{t.settings_level_placeholder}</option>{LEVELS.map((level) => <option value={level} key={level}>{level.replace("_", "/").toUpperCase()}</option>)}</select></label>
        <label className="setup-field"><span>{t.settings_goals} · {t.level_setup_optional}</span><textarea rows={2} value={form.goals} onChange={(event) => setForm({ ...form, goals: event.target.value })} placeholder={t.settings_goals_placeholder} /></label>
        <label className="setup-field"><span>{t.settings_prompt_label} · {t.level_setup_optional}</span><textarea rows={2} value={form.prompt} onChange={(event) => setForm({ ...form, prompt: event.target.value })} placeholder={t.settings_prompt_placeholder} /></label>
        {error && <p className="setup-error" role="alert">{error}</p>}
        <button className="setup-primary" type="submit" disabled={busy}>{busy ? t.app_loading : t.target_lang_start}</button>
      </form>
    </section>
  );
}
