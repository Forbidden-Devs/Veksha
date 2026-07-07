import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useI18n, useT } from "../../shared/i18n";
import { CONFIG } from "../../shared/config";
import { LANGUAGES } from "../../shared/languages";
import { storageSet } from "../../shared/platform";
import { useApp } from "../App";

const LANG_OPTIONS = LANGUAGES.filter((l) => l.code !== "auto");

function detectNativeLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANG_OPTIONS.some((l) => l.code === raw) ? raw : "en";
}

export function SettingsScreen() {
  const { username, settingsMode, navigateTo, setLangPair, targetLang: appTargetLang, nativeLang: appNativeLang } = useApp();
  const { switchLanguage, translating } = useI18n();
  const t = useT();

  const [level, setLevel] = useState("");
  const [goals, setGoals] = useState("");
  const [prompt, setPrompt] = useState("");
  const [nativeLang, setNativeLang] = useState(() => appNativeLang || detectNativeLang());
  const [targetLang, setTargetLang] = useState(() => appTargetLang || "en");
  const [reminderLevel, setReminderLevel] = useState(2);
  const [overseer, setOverseer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  const isOnboarding = settingsMode === "onboarding";

  // CEFR grade scale (labels are universal codes — no translation needed).
  const ENGLISH_LEVELS = [
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

  useEffect(() => {
    let alive = true;
    setLoadingSettings(true);
    setSettingsLoaded(false);
    setError(null);
    api.getSettings(username).then((s) => {
      if (!alive) return;
      setLevel(s.english_level ?? "");
      setGoals(s.goals);
      setPrompt(s.general_prompt);
      setNativeLang(s.native_lang || detectNativeLang());
      setTargetLang(s.target_lang || "en");
      setReminderLevel(s.reminder_level ?? 2);
      setOverseer(s.overseer ?? false);
      setSettingsLoaded(true);
    }).catch((err) => {
      if (!alive) return;
      setNativeLang(appNativeLang || detectNativeLang());
      setTargetLang(appTargetLang || "en");
      setError(`${t.settings_err_load}: ${(err as Error).message}`);
    }).finally(() => {
      if (alive) setLoadingSettings(false);
    });
    return () => { alive = false; };
  }, [username, appNativeLang, appTargetLang, t.settings_err_load]);

  async function handleSave() {
    if (loadingSettings || !settingsLoaded) return;
    if (!level) { setError(t.settings_err_no_level); return; }
    if (nativeLang === targetLang) { setError(t.settings_err_same_lang); return; }
    setError(null);
    setSaving(true);
    try {
      await api.saveSettings(username, {
        englishLevel: level,
        goals,
        generalPrompt: prompt,
        nativeLang,
        targetLang,
        reminderLevel,
        overseer,
      });
      storageSet({ [CONFIG.STORAGE_KEY_NATIVE_LANG]: nativeLang });
      setLangPair(targetLang, nativeLang);
      await switchLanguage(nativeLang);
      navigateTo("chat");
    } catch (err) {
      setError(`${t.settings_err_save}: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  function btnLabel() {
    if (translating) return t.settings_translating;
    if (saving) return t.settings_saving;
    return t.settings_save;
  }

  return (
    <section className="screen screen-settings">
      <header className="menu-header">
        <span className="menu-title">{t.settings_title}</span>
        {!isOnboarding && (
          <button className="icon-btn" aria-label="Close" style={{ marginLeft: "auto" }} onClick={() => navigateTo("chat")}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        )}
      </header>

      <div className="settings-body">
        {loadingSettings && (
          <p className="settings-intro">{t.app_loading}</p>
        )}

        {isOnboarding && (
          <p className="settings-intro">{t.settings_intro}</p>
        )}

        <label className="field-label" htmlFor="settings-native-lang">{t.settings_native_lang}</label>
        <select
          id="settings-native-lang"
          className="select-input"
          value={nativeLang}
          onChange={(e) => setNativeLang(e.target.value)}
        >
          {LANG_OPTIONS.map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>

        <label className="field-label" htmlFor="settings-target-lang">{t.settings_target_lang}</label>
        <select
          id="settings-target-lang"
          className="select-input"
          value={targetLang}
          onChange={(e) => setTargetLang(e.target.value)}
        >
          {LANG_OPTIONS.map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>

        <label className="field-label" htmlFor="settings-level">{t.settings_level}</label>
        <select
          id="settings-level"
          className="select-input"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option value="" disabled>{t.settings_level_placeholder}</option>
          {ENGLISH_LEVELS.map((l) => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </select>

        <label className="field-label" htmlFor="settings-goals">{t.settings_goals}</label>
        <textarea
          id="settings-goals"
          className="textarea-input"
          rows={3}
          placeholder={t.settings_goals_placeholder}
          value={goals}
          onChange={(e) => setGoals(e.target.value)}
        />

        <label className="field-label" htmlFor="settings-prompt">{t.settings_prompt_label}</label>
        <textarea
          id="settings-prompt"
          className="textarea-input"
          rows={3}
          placeholder={t.settings_prompt_placeholder}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        <div className="settings-level">
          <span className="settings-toggle-title">{t.settings_reminder_level}</span>
          <span className="settings-toggle-desc">{t.settings_reminder_level_desc}</span>
          <input
            type="range"
            className="settings-level-range"
            min={1}
            max={3}
            step={1}
            value={reminderLevel}
            onChange={(e) => setReminderLevel(Number(e.target.value))}
          />
          <div className="settings-level-ticks">
            <button
              type="button"
              className={reminderLevel === 1 ? "is-active" : ""}
              onClick={() => setReminderLevel(1)}
            >
              {t.settings_reminder_level_1}
            </button>
            <button
              type="button"
              className={reminderLevel === 2 ? "is-active" : ""}
              onClick={() => setReminderLevel(2)}
            >
              {t.settings_reminder_level_2}
            </button>
            <button
              type="button"
              className={reminderLevel === 3 ? "is-active" : ""}
              onClick={() => setReminderLevel(3)}
            >
              {t.settings_reminder_level_3}
            </button>
          </div>
        </div>

        <label className={`settings-toggle${reminderLevel < 2 ? " is-disabled" : ""}`}>
          <span className="settings-toggle-copy">
            <span className="settings-toggle-title">{t.settings_persistent}</span>
            <span className="settings-toggle-desc">{t.settings_persistent_desc}</span>
          </span>
          <input
            type="checkbox"
            checked={overseer}
            disabled={reminderLevel < 2}
            onChange={(e) => setOverseer(e.target.checked)}
          />
          <span className="settings-toggle-slider" aria-hidden="true" />
        </label>

        {error && <p className="onboarding-error">{error}</p>}
      </div>

      <div className="settings-footer">
        <button className="btn btn-gradient btn-block" disabled={saving || translating || loadingSettings || !settingsLoaded} onClick={handleSave}>
          {btnLabel()}
        </button>
      </div>

    </section>
  );
}
