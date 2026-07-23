import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { isExtension, storageGet, storageSet } from "../../shared/platform";
import type { SettingsData } from "../../shared/types";
import {
  blockAiOnPage,
  blockAiOnSite,
  enableAiOnPage,
  enableAiOnSite,
  isAiBlocked,
  normalizeAiBlocklist,
  pageKey,
  type AiBlocklist,
} from "../../shared/aiBlocklist";
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
  aiBlock: <svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.7 2.8 8.1 7 10 4.2-1.9 7-5.3 7-10V6l-7-3Z"/><path d="m8 16 8-8"/><circle cx="9" cy="9" r="1"/><circle cx="15" cy="15" r="1"/></svg>,
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
  const [activeUrl, setActiveUrl] = useState("");
  const [aiBlocklist, setAiBlocklist] = useState<AiBlocklist>({ sites: [], pages: [], allowedPages: [] });
  const [blockDialogOpen, setBlockDialogOpen] = useState(false);
  const [featureGuide, setFeatureGuide] = useState<"ci_meter" | "dual_subtitles" | null>(null);
  const [quickText, setQuickText] = useState("");
  const [quickResult, setQuickResult] = useState<string | null>(null);
  const [quickLoading, setQuickLoading] = useState(false);
  const [quickError, setQuickError] = useState(false);
  const aiBlockAvailable = pageKey(activeUrl) !== null;
  const aiBlocked = aiBlockAvailable && isAiBlocked(activeUrl, aiBlocklist);

  useEffect(() => {
    if (!featureGuide) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFeatureGuide(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [featureGuide]);

  useEffect(() => {
    Promise.all([api.getKbSummary(username), api.getReminders(username)])
      .then(([kb, rem]) => setCounts({ words: kb.learning_count + kb.known_count, due: rem.due_words }))
      .catch(() => {});
  }, [username]);

  async function handleQuickTranslate(event: React.FormEvent) {
    event.preventDefault();
    const text = quickText.trim();
    if (!text || quickLoading) return;
    setQuickLoading(true);
    setQuickError(false);
    setQuickResult(null);
    try {
      const result = await api.quickTranslate(username, text, nativeLang, targetLang, true);
      setQuickResult(result.translation);
      const [kb, reminders] = await Promise.all([
        api.getKbSummary(username),
        api.getReminders(username),
      ]);
      setCounts({ words: kb.learning_count + kb.known_count, due: reminders.due_words });
    } catch {
      setQuickError(true);
    } finally {
      setQuickLoading(false);
    }
  }

  useEffect(() => {
    storageGet([
      CONFIG.STORAGE_KEY_CI_METER,
      CONFIG.STORAGE_KEY_GRAMMAR_LENS,
      CONFIG.STORAGE_KEY_IMMERSION,
      CONFIG.STORAGE_KEY_VOCAB_FREQ,
      CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE,
      CONFIG.STORAGE_KEY_DUAL_SUBS,
      CONFIG.STORAGE_KEY_AI_BLOCKLIST,
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
      setAiBlocklist(normalizeAiBlocklist(result[CONFIG.STORAGE_KEY_AI_BLOCKLIST]));
    });
    if (isExtension) {
      chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => setActiveUrl(tab?.url ?? "")).catch(() => {});
    }
  }, []);

  async function updateAiBlocklist(next: AiBlocklist) {
    setAiBlocklist(next);
    setBlockDialogOpen(false);
    await storageSet({ [CONFIG.STORAGE_KEY_AI_BLOCKLIST]: next });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_AI_BLOCKLIST_UPDATED" });
    } catch { /* restricted pages simply use the saved preference later */ }
  }

  function chooseAiBlock(scope: "page" | "site") {
    if (!activeUrl) return;
    const next = aiBlocked
      ? scope === "page" ? enableAiOnPage(aiBlocklist, activeUrl) : enableAiOnSite(aiBlocklist, activeUrl)
      : scope === "page" ? blockAiOnPage(aiBlocklist, activeUrl) : blockAiOnSite(aiBlocklist, activeUrl);
    void updateAiBlocklist(next);
  }

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

  if (!isExtension) {
    const languageName = LANGUAGES.find((lang) => lang.code === targetLang)?.name ?? targetLang.toUpperCase();
    return (
      <section className="screen screen-home web-home">
        <div className="web-home-hero">
          <div className="web-home-kicker">{languageName} · {targetLang.toUpperCase()}</div>
          <h1>{t.tour_s0_title.replace("|", " ")}</h1>
          <p>{t.tutorial_s4_body}</p>
          <form className="web-quick-add" onSubmit={handleQuickTranslate}>
            <input
              type="text"
              value={quickText}
              onChange={(event) => setQuickText(event.target.value)}
              placeholder={t.dictionary_search_placeholder}
              autoCapitalize="none"
              autoComplete="off"
              maxLength={500}
              aria-label={t.chat_mode_translate}
            />
            <button type="submit" disabled={!quickText.trim() || quickLoading}>
              {quickLoading ? "…" : "→"}
            </button>
          </form>
          {quickResult && (
            <button className="web-quick-result" type="button" onClick={() => navigateTo("dictionary")}>
              <span>{quickResult}</span><small>{t.tour_saved}</small>
            </button>
          )}
          {quickError && <p className="web-quick-error">Translation unavailable. Try again.</p>}
        </div>

        <div className="web-today-grid">
          <button className="web-today-card is-primary" onClick={openTraining}>
            <span className="web-today-value">{counts?.due ?? "…"}</span>
            <span>{t.stats_ready}</span>
            <strong>{t.nav_training} →</strong>
          </button>
          <button className="web-today-card" onClick={() => navigateTo("dictionary")}>
            <span className="web-today-value">{counts?.words ?? "…"}</span>
            <span>{t.dictionary_title}</span>
            <strong>{t.dictionary_cards} →</strong>
          </button>
        </div>

        <div className="web-action-grid">
          <button onClick={() => navigateTo("translator")}><span>{Icons.dictionary}</span><strong>{t.chat_mode_translate}</strong></button>
          <button onClick={() => navigateTo("topics")}><span>{Icons.topics}</span><strong>{t.nav_topics}</strong><small>{t.sub_topics}</small></button>
          <button onClick={() => navigateTo("statistics")}><span>{Icons.stats}</span><strong>{t.nav_stats}</strong></button>
          <button onClick={() => navigateTo("settings", { settingsMode: "menu" })}><span>{Icons.settings}</span><strong>{t.nav_settings}</strong></button>
        </div>

        <button className="web-language-switch" onClick={switchTargetLanguage} disabled={!settings || (settings.target_langs?.length ?? 1) < 2}>
          <span>{Icons.language}</span>
          <span>{languageName}</span>
          <strong>{targetLang.toUpperCase()}</strong>
        </button>
      </section>
    );
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
            className={`m-tile m-feature-tile ${aiBlocked ? "is-blocked" : immersionOn ? "is-on" : "is-off"}`}
            onClick={openImmersion} disabled={aiBlocked}
          >
            <span className="m-tile-icon">{Icons.immersion}</span>
            <span className="m-tile-label">{t.nav_immersion}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {aiBlocked ? t.feature_blocked : immersionOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        ) : <div className="m-tile m-tile-ghost" aria-hidden="true" />}
        {isExtension && (
          <div className="m-feature-guide-wrap">
            <button
              className={`m-tile m-feature-tile ${aiBlocked ? "is-blocked" : dualSubsEnabled ? "is-on" : "is-off"}`}
              onClick={toggleDualSubtitles}
              disabled={aiBlocked}
              aria-pressed={dualSubsEnabled}
            >
              <span className="m-tile-icon">{Icons.dualSubtitles}</span>
              <span className="m-tile-label">{t.settings_dual_subtitles}</span>
              <span className="m-feature-state">
                <i aria-hidden="true" />
                {aiBlocked ? t.feature_blocked : dualSubsEnabled ? t.feature_enabled : t.feature_disabled}
              </span>
            </button>
            <button
              type="button"
              className="m-feature-guide-button"
              aria-label={`${t.feature_guide_open}: ${t.settings_dual_subtitles}`}
              title={t.feature_guide_open}
              onClick={() => setFeatureGuide("dual_subtitles")}
            >?</button>
          </div>
        )}
        {isExtension && (
          <button
            className={`m-tile m-feature-tile ${aiBlocked ? "is-blocked" : grammarLensOn ? "is-on" : "is-off"}`}
            onClick={toggleGrammarLens}
            disabled={aiBlocked}
            aria-pressed={grammarLensOn}
          >
            <span className="m-tile-icon">{Icons.grammar}</span>
            <span className="m-tile-label">{t.grammar_lens_title}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {aiBlocked ? t.feature_blocked : grammarLensOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        )}
        {isExtension && (
          <div className="m-feature-guide-wrap">
            <button
              className={`m-tile m-feature-tile ${aiBlocked ? "is-blocked" : ciMeterOn ? "is-on" : "is-off"}`}
              onClick={toggleCiMeter}
              disabled={aiBlocked}
              aria-pressed={ciMeterOn}
            >
              <span className="m-tile-icon">{Icons.ciMeter}</span>
              <span className="m-tile-label">{t.ci_meter_off}</span>
              <span className="m-feature-state">
                <i aria-hidden="true" />
                {aiBlocked ? t.feature_blocked : ciMeterOn ? t.feature_enabled : t.feature_disabled}
              </span>
            </button>
            <button
              type="button"
              className="m-feature-guide-button"
              aria-label={`${t.feature_guide_open}: ${t.ci_meter_off}`}
              title={t.feature_guide_open}
              onClick={() => setFeatureGuide("ci_meter")}
            >?</button>
          </div>
        )}
        {isExtension && (
          <button
            className={`m-tile m-feature-tile ${aiBlocked ? "is-blocked" : vocabFreqOn ? "is-on" : "is-off"}`}
            onClick={() => navigateTo("myWords")}
            disabled={aiBlocked}
          >
            <span className="m-tile-icon">{Icons.myWords}</span>
            <span className="m-tile-label">{t.my_words_title}</span>
            <span className="m-feature-state">
              <i aria-hidden="true" />
              {aiBlocked ? t.feature_blocked : vocabFreqOn ? t.feature_enabled : t.feature_disabled}
            </span>
          </button>
        )}

        {isExtension && (
          <button
            className={`m-tile m-feature-tile m-ai-block-tile ${aiBlocked ? "is-on" : "is-off"}`}
            onClick={() => setBlockDialogOpen(true)}
            disabled={!aiBlockAvailable}
          >
            <span className="m-tile-icon">{Icons.aiBlock}</span>
            <span className="m-tile-label">{t.ai_block_title}</span>
            <span className="m-feature-state"><i aria-hidden="true" />{aiBlocked ? t.ai_block_enabled : t.feature_disabled}</span>
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
      {blockDialogOpen && (
        <div className="ai-block-dialog-backdrop" role="presentation" onMouseDown={() => setBlockDialogOpen(false)}>
          <div className="ai-block-dialog" role="dialog" aria-modal="true" aria-labelledby="ai-block-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="ai-block-dialog-close" onClick={() => setBlockDialogOpen(false)} aria-label="Close">×</button>
            <span className="ai-block-dialog-icon">{Icons.aiBlock}</span>
            <h2 id="ai-block-title">{t.ai_block_title}</h2>
            <div className="ai-block-dialog-actions">
              <button onClick={() => chooseAiBlock("page")}>{aiBlocked ? t.ai_block_enable_page : t.ai_block_disable_page}</button>
              <button onClick={() => chooseAiBlock("site")}>{aiBlocked ? t.ai_block_enable_site : t.ai_block_disable_site}</button>
            </div>
            <p>{t.ai_block_dialog_hint}</p>
          </div>
        </div>
      )}
      {featureGuide && (
        <div className="feature-guide-backdrop" role="presentation" onMouseDown={() => setFeatureGuide(null)}>
          <div
            className="feature-guide-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="feature-guide-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="feature-guide-close" onClick={() => setFeatureGuide(null)} aria-label={t.feature_guide_close}>×</button>
            <span className="feature-guide-icon" aria-hidden="true">
              {featureGuide === "ci_meter" ? Icons.ciMeter : Icons.dualSubtitles}
            </span>
            <h2 id="feature-guide-title">
              {featureGuide === "ci_meter" ? t.ci_meter_guide_title : t.dual_subtitles_guide_title}
            </h2>
            <p className="feature-guide-intro">
              {featureGuide === "ci_meter" ? t.ci_meter_guide_intro : t.dual_subtitles_guide_intro}
            </p>
            <ol>
              {(featureGuide === "ci_meter"
                ? [t.ci_meter_guide_step_1, t.ci_meter_guide_step_2, t.ci_meter_guide_step_3]
                : [t.dual_subtitles_guide_step_1, t.dual_subtitles_guide_step_2, t.dual_subtitles_guide_step_3]
              ).map((step, index) => <li key={index}>{step}</li>)}
            </ol>
            <p className="feature-guide-tip">
              {featureGuide === "ci_meter" ? t.ci_meter_guide_tip : t.dual_subtitles_guide_tip}
            </p>
            <button className="btn btn-gradient btn-block" type="button" onClick={() => setFeatureGuide(null)}>
              {t.feature_guide_close}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
