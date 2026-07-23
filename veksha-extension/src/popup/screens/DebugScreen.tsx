import { useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useI18n, useT } from "../../shared/i18n";
import { runtimeSend, storageGetAll, storageRemove } from "../../shared/platform";
import { useApp } from "../App";

interface CommandResult {
  ok: boolean;
  message: string;
}

export function DebugScreen() {
  const { username, navigateTo } = useApp();
  const t = useT();
  const { regenerate } = useI18n();
  const [result, setResult] = useState<CommandResult | null>(null);
  const [loading, setLoading] = useState(false);

  const detectedLang = (navigator.languages?.[0] ?? navigator.language ?? "?").toLowerCase();

  async function runCommand(command: () => Promise<CommandResult>) {
    setLoading(true);
    setResult(null);
    try {
      setResult(await command());
    } catch (err) {
      setResult({ ok: false, message: `${(err as Error).message}` });
    } finally {
      setLoading(false);
    }
  }

  function handleSimulateTraining() {
    return runCommand(async () => {
      const res = await api.debugSimulateTraining(username);
      return {
        ok: true,
        message: `${res.words_updated} words updated. Topic: ${res.topic_updated ?? "none"}.`,
      };
    });
  }

  function handleRegenI18n() {
    return runCommand(async () => {
      const lang = await regenerate();
      return { ok: true, message: t.debug_regen_done.replace("{lang}", lang) };
    });
  }

  function handleAdvanceDay() {
    return runCommand(async () => {
      const res = await api.debugAdvanceDay(username);
      runtimeSend({ type: "DEBUG_SHOW_REMINDER", reminder: res.reminder });
      return {
        ok: true,
        message: `${res.words_shifted} dates shifted. Due now: ${res.reminder.due_words}.`,
      };
    });
  }

  async function handleReset() {
    if (!confirm(t.debug_reset_confirm.replace("{username}", username))) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await api.debugReset(username);
      // Clear i18n caches so translations are freshly generated. The account
      // (username + token) is kept — the backend wipes data, not the user.
      const all = await storageGetAll();
      const i18nKeys = Object.keys(all).filter((k) => k.startsWith("vk_i18n_"));
      await storageRemove([CONFIG.STORAGE_KEY_NATIVE_LANG, ...i18nKeys]);
      setResult({ ok: true, message: `Deleted: ${res.deleted.join(", ") || "nothing"}. ${t.debug_reloading}` });
      setTimeout(() => window.close(), 1200);
    } catch (err) {
      setResult({ ok: false, message: `${(err as Error).message}` });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="screen screen-settings">
      <header className="menu-header">
        <button className="icon-btn" aria-label="Back" onClick={() => navigateTo("home")}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <span className="menu-title">&#128295; {t.debug_title}</span>
      </header>

      <div className="settings-body">
        <div className="debug-info-block">
          <div className="debug-info-row">
            <span className="debug-info-label">{t.debug_user}</span>
            <span className="debug-info-value">{username}</span>
          </div>
          <div className="debug-info-row">
            <span className="debug-info-label">{t.debug_backend}</span>
            <span className="debug-info-value">{CONFIG.BACKEND_URL}</span>
          </div>
          <div className="debug-info-row">
            <span className="debug-info-label">{t.debug_browser_lang}</span>
            <span className="debug-info-value">{detectedLang}</span>
          </div>
          <div className="debug-info-row">
            <span className="debug-info-label">{t.debug_all_langs}</span>
            <span className="debug-info-value">{[...(navigator.languages ?? [navigator.language])].join(", ")}</span>
          </div>
        </div>

        <p className="field-label" style={{ marginTop: 16 }}>{t.debug_commands}</p>

        <div className="debug-command-card">
          <div className="debug-command-info">
            <span className="debug-command-name">{t.debug_simulate_training_name}</span>
            <span className="debug-command-desc">{t.debug_simulate_training_desc}</span>
          </div>
          <button className="btn debug-command-btn" onClick={handleSimulateTraining} disabled={loading}>
            {loading ? "…" : t.debug_run}
          </button>
        </div>

        <div className="debug-command-card">
          <div className="debug-command-info">
            <span className="debug-command-name">{t.debug_advance_day_name}</span>
            <span className="debug-command-desc">{t.debug_advance_day_desc}</span>
          </div>
          <button className="btn debug-command-btn" onClick={handleAdvanceDay} disabled={loading}>
            {loading ? "…" : t.debug_run}
          </button>
        </div>

        <div className="debug-command-card">
          <div className="debug-command-info">
            <span className="debug-command-name">{t.debug_regen_name}</span>
            <span className="debug-command-desc">{t.debug_regen_desc}</span>
          </div>
          <button className="btn debug-command-btn" onClick={handleRegenI18n} disabled={loading}>
            {loading ? "…" : t.debug_run}
          </button>
        </div>

        <div className="debug-command-card">
          <div className="debug-command-info">
            <span className="debug-command-name">{t.debug_reset_name}</span>
            <span className="debug-command-desc">{t.debug_reset_desc}</span>
          </div>
          <button
            className="btn debug-command-btn"
            onClick={handleReset}
            disabled={loading}
          >
            {loading ? "…" : t.debug_run}
          </button>
        </div>

        {result && (
          <p className={result.ok ? "debug-result-ok" : "onboarding-error"}>
            {result.message}
          </p>
        )}
      </div>
    </section>
  );
}
