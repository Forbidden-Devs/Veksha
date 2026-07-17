import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { isExtension, storageGet, storageSet } from "../../shared/platform";
import type { SettingsData } from "../../shared/types";
import { useApp } from "../App";

/**
 * HomeScreen — Metro start screen with a compact feature tile grid.
 *
 * Layout (mirrors the paper sketch):
 *   [dictionary] [topics] [training] [immersion]
 *   [dual subs] [grammar] [CI meter] [my words]
 *   [statistics] [settings] [          language          ]
 */

const Icons = {
  dictionary: <svg viewBox="0 0 24 24"><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22V5.5Z"/><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22V5.5Z"/></svg>,
  topics: <svg viewBox="0 0 24 24"><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>,
  training: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m15 9 5-5M16 4h4v4"/></svg>,
  immersion: <svg viewBox="0 0 24 24"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/><circle cx="12" cy="12" r="3.5"/></svg>,
  ciMeter: <svg viewBox="0 0 24 24"><path d="M4 18a8 8 0 0 1 16 0"/><path d="M12 18l4.5-6"/><circle cx="12" cy="18" r="1.2"/></svg>,
  stats: <svg viewBox="0 0 24 24"><path d="M5 20V10h4v10M10 20V4h4v16M15 20v-7h4v7M3 20h18"/></svg>,
  settings: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>,
  language: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3Z"/></svg>,
  grammar: <svg viewBox="0 0 24 24"><path d="M8 4H5v16h3M16 4h3v16h-3M10 8h4M10 12h4M10 16h4"/></svg>,
  dualSubtitles: <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10h4M7 14h7M16 10h1M16 14h1"/></svg>,
  myWords: <svg viewBox="0 0 24 24"><path d="M4 19V6a2 2 0 0 1 2-2h11l3 3v12a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2Z"/><path d="M8 9h8M8 13h5"/></svg>,
};

export function HomeScreen() {
  const { username, navigateTo, openTraining, requirePremiumFeature, targetLang, nativeLang, setLangPair } = useApp();
  const t = useT();
  const [counts, setCounts] = useState<{ words: number; due: number } | null>(null);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [ciMeterOn, setCiMeterOn] = useState(false);
  const [grammarLensOn, setGrammarLensOn] = useState(false);
  const [immersionOn, setImmersionOn] = useState(false);
  const [vocabFreqOn, setVocabFreqOn] = useState(false);
  const [dualSubsEnabled, setDualSubsEnabled] = useState(false);

  useEffect(() => {
    Promise.all([api.getKbSummary(username), api.getReminders(username)])
      .then(([kb, rem]) => setCounts({ words: kb.learning_count + kb.known_count, due: rem.due_words }))
      .catch(() => {});
  }, [username]);

  useEffect(() => {
    storageGet([
      CONFIG.STORAGE_KEY_CI_METER,
      CONFIG.STORAGE_KEY_GRAMMAR_LENS,
      CONFIG.STORAGE_KEY_IMMERSION,
      CONFIG.STORAGE_KEY_VOCAB_FREQ,
      CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE,
      CONFIG.STORAGE_KEY_DUAL_SUBS,
    ]).then((result) => {
      setCiMeterOn(Boolean(result[CONFIG.STORAGE_KEY_CI_METER]));
      setGrammarLensOn(Boolean(result[CONFIG.STORAGE_KEY_GRAMMAR_LENS]));
      setImmersionOn(Boolean(result[CONFIG.STORAGE_KEY_IMMERSION]));
      setVocabFreqOn(Boolean(result[CONFIG.STORAGE_KEY_VOCAB_FREQ]));
      const storedDualSubsFeature = result[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE];
      const legacyDualSubsEnabled = Boolean(result[CONFIG.STORAGE_KEY_DUAL_SUBS]);
      const dualSubsFeatureEnabled = storedDualSubsFeature === undefined
        ? legacyDualSubsEnabled
        : Boolean(storedDualSubsFeature);
      setDualSubsEnabled(dualSubsFeatureEnabled);
      if (storedDualSubsFeature === undefined && legacyDualSubsEnabled) {
        storageSet({ [CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]: true });
      }
    });
  }, []);

  async function toggleCiMeter() {
    const next = !ciMeterOn;
    setCiMeterOn(next);
    await storageSet({ [CONFIG.STORAGE_KEY_CI_METER]: next });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_CI_METER", enabled: next });
      }
    } catch {
      // Restricted pages cannot receive content-script messages; the saved
      // preference will still be applied on the next regular page.
    }
  }

  async function toggleGrammarLens() {
    const next = !grammarLensOn;
    if (next && !(await requirePremiumFeature("grammar_lens", t.grammar_lens_title))) return;
    setGrammarLensOn(next);
    if (next) setImmersionOn(false);
    await storageSet({
      [CONFIG.STORAGE_KEY_GRAMMAR_LENS]: next,
      ...(next ? { [CONFIG.STORAGE_KEY_IMMERSION]: false } : {}),
    });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        if (next) await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_IMMERSION", enabled: false });
        await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_GRAMMAR_LENS", enabled: next });
      }
    } catch {
      // The saved preference is applied on the next regular page.
    }
  }

  async function openImmersion() {
    // Always let a user reach the screen to turn off a stale enabled setting;
    // only entering the paid feature from the off state requires Premium.
    if (immersionOn || await requirePremiumFeature("immersion", t.nav_immersion)) {
      navigateTo("immersion");
    }
  }

  async function toggleDualSubtitles() {
    const next = !dualSubsEnabled;
    if (next && !(await requirePremiumFeature("dual_subtitles", t.settings_dual_subtitles))) return;
    setDualSubsEnabled(next);
    try {
      await storageSet({
        [CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]: next,
        ...(next ? { [CONFIG.STORAGE_KEY_DUAL_SUBS]: true } : {}),
      });
    } catch {
      setDualSubsEnabled(!next);
    }
  }

  useEffect(() => { api.getSettings(username).then(setSettings).catch(() => {}); }, [username, targetLang]);

  async function switchTargetLanguage() {
    if (!settings) return;
    const languages = settings.target_langs?.length ? settings.target_langs : [settings.target_lang];
    if (languages.length < 2) return;
    const next = languages[(languages.indexOf(targetLang) + 1) % languages.length];
    const prefs = settings.language_settings?.[next] ?? { level: "", goals: "", prompt: "" };
    const updated = await api.saveSettings(username, {
      displayName: settings.display_name,
      englishLevel: prefs.level,
      goals: prefs.goals,
      generalPrompt: prefs.prompt,
      nativeLang,
      targetLang: next,
      targetLangs: languages,
      languageSettings: settings.language_settings,
      reminderLevel: settings.reminder_level,
      overseer: settings.overseer,
    });
    setSettings(updated);
    setLangPair(next, nativeLang);
  }

  return (
    <section className="screen screen-home">
      <div className="m-tiles">
        <button className="m-tile" onClick={() => navigateTo("dictionary")}>
          <span className="m-tile-icon">{Icons.dictionary}</span>
          <span className="m-tile-label">{t.dictionary_title}</span>
        </button>
        <button className="m-tile" onClick={() => navigateTo("topics")}>
          <span className="m-tile-icon">{Icons.topics}</span>
          <span className="m-tile-label">{t.nav_topics}</span>
        </button>
        <button className="m-tile" onClick={openTraining}>
          <span className="m-tile-icon">{Icons.training}</span>
          {counts !== null && counts.due > 0 && <span className="m-tile-badge">{counts.due}</span>}
          <span className="m-tile-label">{t.nav_training}</span>
        </button>
        {isExtension ? (
          <button
            className={`m-tile m-feature-tile ${immersionOn ? "is-on" : "is-off"}`}
            onClick={openImmersion}
          >
            <span className="m-tile-icon">{Icons.immersion}</span>
            <span className="m-tile-label">{t.nav_immersion}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {immersionOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        ) : <div className="m-tile m-tile-ghost" aria-hidden="true" />}
        {isExtension && (
          <button
            className={`m-tile m-feature-tile ${dualSubsEnabled ? "is-on" : "is-off"}`}
            onClick={toggleDualSubtitles}
            aria-pressed={dualSubsEnabled}
          >
            <span className="m-tile-icon">{Icons.dualSubtitles}</span>
            <span className="m-tile-label">{t.settings_dual_subtitles}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {dualSubsEnabled ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        )}
        {isExtension && (
          <button
            className={`m-tile m-feature-tile ${grammarLensOn ? "is-on" : "is-off"}`}
            onClick={toggleGrammarLens}
            aria-pressed={grammarLensOn}
          >
            <span className="m-tile-icon">{Icons.grammar}</span>
            <span className="m-tile-label">{t.grammar_lens_title}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {grammarLensOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        )}
        {isExtension && (
          <button
            className={`m-tile m-feature-tile ${ciMeterOn ? "is-on" : "is-off"}`}
            onClick={toggleCiMeter}
            aria-pressed={ciMeterOn}
          >
            <span className="m-tile-icon">{Icons.ciMeter}</span>
            <span className="m-tile-label">{t.ci_meter_off}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {ciMeterOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        )}
        {isExtension && (
          <button
            className={`m-tile m-feature-tile ${vocabFreqOn ? "is-on" : "is-off"}`}
            onClick={() => navigateTo("myWords")}
          >
            <span className="m-tile-icon">{Icons.myWords}</span>
            <span className="m-tile-label">{t.my_words_title}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {vocabFreqOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        )}

        <button className="m-tile m-tile-stats" onClick={() => navigateTo("statistics")}>
          <span className="m-tile-icon">{Icons.stats}</span>
          <span className="m-tile-label">{t.nav_stats}</span>
          <span className="m-tile-badge">{counts?.words ?? "…"}</span>
        </button>
        <button className="m-tile" onClick={() => navigateTo("settings", { settingsMode: "menu" })}>
          <span className="m-tile-icon">{Icons.settings}</span>
          <span className="m-tile-label">{t.nav_settings}</span>
        </button>
        <button className="m-tile m-tile-wide m-tile-alt" onClick={switchTargetLanguage} disabled={!settings || (settings.target_langs?.length ?? 1) < 2}>
          <span className="m-tile-icon">{Icons.language}</span>
          <span className="m-tile-badge">{targetLang.toUpperCase()}</span>
          <span className="m-tile-label">{LANGUAGES.find((lang) => lang.code === targetLang)?.name ?? targetLang}</span>
        </button>
      </div>
    </section>
  );
}
