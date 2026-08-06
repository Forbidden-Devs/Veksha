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

/** HomeScreen — launch surface for learning tools and page-level controls. */

const Icons = {
  dictionary: <svg viewBox="0 0 24 24"><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22V5.5Z"/><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22V5.5Z"/></svg>,
  topics: <svg viewBox="0 0 24 24"><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>,
  training: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m15 9 5-5M16 4h4v4"/></svg>,
  readingCoach: <svg viewBox="0 0 24 24"><path d="M4 18a8 8 0 0 1 16 0"/><path d="M12 18l4.5-6"/><circle cx="12" cy="18" r="1.2"/></svg>,
  stats: <svg viewBox="0 0 24 24"><path d="M5 20V10h4v10M10 20V4h4v16M15 20v-7h4v7M3 20h18"/></svg>,
  settings: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>,
  language: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3Z"/></svg>,
  grammar: <svg viewBox="0 0 24 24"><path d="M8 4H5v16h3M16 4h3v16h-3M10 8h4M10 12h4M10 16h4"/></svg>,
  dualSubtitles: <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 10h4M7 14h7M16 10h1M16 14h1"/></svg>,
  myWords: <svg viewBox="0 0 24 24"><path d="M4 19V6a2 2 0 0 1 2-2h11l3 3v12a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2Z"/><path d="M8 9h8M8 13h5"/></svg>,
  quizlet: <svg viewBox="0 0 24 24"><path d="M5 5h7v7H5V5zm7 0h7v7h-7V5zM5 12h7v7H5v-7zm7 0h7v7h-7v-7z"/></svg>,
  aiBlock: <svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.7 2.8 8.1 7 10 4.2-1.9 7-5.3 7-10V6l-7-3Z"/><path d="m8 16 8-8"/><circle cx="9" cy="9" r="1"/><circle cx="15" cy="15" r="1"/></svg>,
  capture: <svg viewBox="0 0 24 24"><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/><path d="M8 12h8M12 8v8"/></svg>,
};

export function HomeScreen() {
  const { username, navigateTo, openTraining, requirePremiumFeature, targetLang, nativeLang, setLangPair } = useApp();
  const t = useT();
  const [counts, setCounts] = useState<{ words: number; due: number } | null>(null);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [readingCoachOn, setReadingCoachOn] = useState(false);
  const [readingSessionOn, setReadingSessionOn] = useState(false);
  const [dualSubsEnabled, setDualSubsEnabled] = useState(false);
  const [subtitleStudyOn, setSubtitleStudyOn] = useState(false);
  const [activeUrl, setActiveUrl] = useState("");
  const [aiBlocklist, setAiBlocklist] = useState<AiBlocklist>({ sites: [], pages: [], allowedPages: [] });
  const [blockDialogOpen, setBlockDialogOpen] = useState(false);
  const [featureGuide, setFeatureGuide] = useState<"reading_coach" | "dual_subtitles" | "pattern_workshop" | "my_words" | null>(null);
  const [quickText, setQuickText] = useState("");
  const [quickResult, setQuickResult] = useState<string | null>(null);
  const [quickVocabularyMode, setQuickVocabularyMode] = useState<"saved" | "suggested">("saved");
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
      setQuickVocabularyMode(result.vocabulary_mode ?? "saved");
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
      CONFIG.STORAGE_KEY_READING_COACH,
      CONFIG.STORAGE_KEY_READING_SESSION,
      CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE,
      CONFIG.STORAGE_KEY_SUBTITLE_STUDY,
      CONFIG.STORAGE_KEY_AI_BLOCKLIST,
    ]).then((result) => {
      setReadingCoachOn(Boolean(result[CONFIG.STORAGE_KEY_READING_COACH]));
      setReadingSessionOn(Boolean(result[CONFIG.STORAGE_KEY_READING_SESSION]));
      setDualSubsEnabled(Boolean(result[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]));
      setSubtitleStudyOn(Boolean(result[CONFIG.STORAGE_KEY_SUBTITLE_STUDY]));
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

  async function toggleReadingCoach() {
    const next = !readingCoachOn;
    setReadingCoachOn(next);
    await storageSet({ [CONFIG.STORAGE_KEY_READING_COACH]: next });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_READING_COACH", enabled: next });
      }
    } catch {
      // Restricted pages cannot receive content-script messages; the saved
      // preference will still be applied on the next regular page.
    }
  }

  async function openAreaTranslation() {
    try {
      await chrome.runtime.sendMessage({ type: "VEKSHA_START_REGION_CAPTURE" });
    } catch {
      // Browser-protected pages cannot be captured; keep the popup responsive.
    }
  }

  async function toggleDualSubtitles() {
    const next = !dualSubsEnabled;
    if (next && !(await requirePremiumFeature("dual_subtitles", t.settings_dual_subtitles))) return;
    const studyWas = subtitleStudyOn;
    setDualSubsEnabled(next);
    // A study session has no translated track to work with once dual subtitles
    // are off, so it goes with them — the mirror of switching them on together.
    if (!next) setSubtitleStudyOn(false);
    try {
      await storageSet({
        [CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]: next,
        [CONFIG.STORAGE_KEY_DUAL_SUBS_VISIBLE]: next,
        ...(!next ? { [CONFIG.STORAGE_KEY_SUBTITLE_STUDY]: false } : {}),
      });
    } catch {
      setDualSubsEnabled(!next);
      setSubtitleStudyOn(studyWas);
    }
  }

  async function toggleSubtitleStudy() {
    const next = !subtitleStudyOn;
    if (next && !(await requirePremiumFeature("dual_subtitles", t.settings_subtitle_study))) return;
    setSubtitleStudyOn(next);
    try {
      // The study session needs a translated track to hide, so switching it on
      // switches dual subtitles on with it.
      await storageSet({
        [CONFIG.STORAGE_KEY_SUBTITLE_STUDY]: next,
        ...(next ? {
          [CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]: true,
          [CONFIG.STORAGE_KEY_DUAL_SUBS_VISIBLE]: true,
        } : {}),
      });
      if (next) setDualSubsEnabled(true);
    } catch {
      setSubtitleStudyOn(!next);
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
    });
    setSettings(updated);
    setLangPair(next, nativeLang);
  }

  if (!isExtension) {
    const languageName = LANGUAGES.find((lang) => lang.code === targetLang)?.name ?? targetLang.toUpperCase();
    return (
      <section className="screen launchpad web-home">
        <div className="web-home-hero">
          <div className="web-home-kicker">{languageName} · {targetLang.toUpperCase()}</div>
          <h1>{t.home_hero_title.replace("|", " ")}</h1>
          <p>{t.home_translation_body}</p>
          <form className="web-quick-add" onSubmit={handleQuickTranslate}>
            <input
              type="text"
              value={quickText}
              onChange={(event) => setQuickText(event.target.value)}
              placeholder={t.dictionary_search_placeholder}
              autoCapitalize="none"
              autoComplete="off"
              maxLength={500}
              aria-label={t.translator_title}
            />
            <button type="submit" disabled={!quickText.trim() || quickLoading}>
              {quickLoading ? "…" : "→"}
            </button>
          </form>
          {quickResult && (
            <button
              className="web-quick-result"
              type="button"
              onClick={() => navigateTo(quickVocabularyMode === "suggested" ? "myWords" : "dictionary")}
            >
              <span>{quickResult}</span>
              <small>
                {quickVocabularyMode === "suggested"
                  ? t.home_quick_suggested
                  : t.home_quick_saved}
              </small>
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
          <button onClick={() => navigateTo("translator")}><span>{Icons.dictionary}</span><strong>{t.translator_title}</strong></button>
          <button onClick={() => navigateTo("goals")}><span>{Icons.topics}</span><strong>{t.lesson_goals_kicker}</strong><small>{t.lesson_goals_hint}</small></button>
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
    <section className="screen launchpad">
      <div className="capability-grid">
        <button className="capability-card capability-card-primary" onClick={openTraining}>
          <span className="capability-card-icon">{Icons.training}</span>
          {counts !== null && counts.due > 0 && <span className="capability-card-badge">{counts.due}</span>}
          <span className="capability-card-label">{t.nav_training}</span>
        </button>
        <button className="capability-card" onClick={() => navigateTo("goals")}>
          <span className="capability-card-icon">{Icons.topics}</span>
          <span className="capability-card-label">{t.lesson_goals_kicker}</span>
        </button>
        <button className="capability-card" onClick={() => navigateTo("dictionary")}>
          <span className="capability-card-icon">{Icons.dictionary}</span>
          <span className="capability-card-label">{t.dictionary_title}</span>
        </button>
        {isExtension && (
          <button className="capability-card" onClick={openAreaTranslation}>
            <span className="capability-card-icon">{Icons.capture}</span>
            <span className="capability-card-label">{t.ocr_translate_area}</span>
          </button>
        )}
        {isExtension && (
          <div className="capability-control">
            <button
              className={`capability-card capability-toggle ${aiBlocked ? "is-blocked" : dualSubsEnabled ? "is-on" : "is-off"}`}
              onClick={toggleDualSubtitles}
              disabled={aiBlocked}
              aria-pressed={dualSubsEnabled}
            >
              <span className="capability-card-icon">{Icons.dualSubtitles}</span>
              <span className="capability-card-label">{t.settings_dual_subtitles}</span>
              <span className="capability-state">
                <i aria-hidden="true" />
                {aiBlocked ? t.feature_blocked : dualSubsEnabled ? t.feature_enabled : t.feature_disabled}
              </span>
            </button>
            <button
              type="button"
              className="capability-help"
              aria-label={`${t.feature_guide_open}: ${t.settings_dual_subtitles}`}
              title={t.feature_guide_open}
              onClick={() => setFeatureGuide("dual_subtitles")}
            >?</button>
          </div>
        )}
        {isExtension && (
          <div className="capability-control">
            <button
              className={`capability-card capability-toggle ${aiBlocked ? "is-blocked" : subtitleStudyOn ? "is-on" : "is-off"}`}
              onClick={toggleSubtitleStudy}
              disabled={aiBlocked}
              aria-pressed={subtitleStudyOn}
            >
              <span className="capability-card-icon">{Icons.dualSubtitles}</span>
              <span className="capability-card-label">{t.settings_subtitle_study}</span>
              <span className="capability-state">
                <i aria-hidden="true" />
                {aiBlocked ? t.feature_blocked : subtitleStudyOn ? t.feature_enabled : t.feature_disabled}
              </span>
            </button>
          </div>
        )}
        {isExtension && (
          <div className="capability-control">
            <button
              className={`capability-card ${aiBlocked ? "is-blocked" : ""}`}
              onClick={() => setFeatureGuide("pattern_workshop")}
              disabled={aiBlocked}
            >
              <span className="capability-card-icon">{Icons.grammar}</span>
              <span className="capability-card-label">{t.pattern_workshop_title}</span>
              <span className="capability-state">
                <i aria-hidden="true" />
                {aiBlocked ? t.feature_blocked : t.pattern_workshop_select_hint}
              </span>
            </button>
            <button
              type="button"
              className="capability-help"
              aria-label={`${t.feature_guide_open}: ${t.pattern_workshop_title}`}
              title={t.feature_guide_open}
              onClick={() => setFeatureGuide("pattern_workshop")}
            >?</button>
          </div>
        )}
        {isExtension && (
          <div className="capability-control">
            <button
              className={`capability-card capability-toggle ${aiBlocked ? "is-blocked" : readingCoachOn ? "is-on" : "is-off"}`}
              onClick={toggleReadingCoach}
              disabled={aiBlocked}
              aria-pressed={readingCoachOn}
            >
              <span className="capability-card-icon">{Icons.readingCoach}</span>
              <span className="capability-card-label">{t.ci_meter_off}</span>
              <span className="capability-state">
                <i aria-hidden="true" />
                {aiBlocked ? t.feature_blocked : readingCoachOn ? t.feature_enabled : t.feature_disabled}
              </span>
            </button>
            <button
              type="button"
              className="capability-help"
              aria-label={`${t.feature_guide_open}: ${t.ci_meter_off}`}
              title={t.feature_guide_open}
              onClick={() => setFeatureGuide("reading_coach")}
            >?</button>
          </div>
        )}
        {isExtension && (
          <div className="capability-control">
            <button
              className={`capability-card capability-toggle capability-destination ${readingSessionOn ? "is-on" : "is-off"}`}
              onClick={() => navigateTo("myWords")}
            >
              <span className="capability-card-icon">{Icons.myWords}</span>
              <span className="capability-card-label">{t.my_words_title}</span>
              <span className="capability-state">
                <i aria-hidden="true" />
                {readingSessionOn ? t.feature_enabled : t.feature_disabled}
              </span>
            </button>
            <button
              type="button"
              className="capability-help"
              aria-label={`${t.feature_guide_open}: ${t.my_words_title}`}
              title={t.feature_guide_open}
              onClick={() => setFeatureGuide("my_words")}
            >?</button>
          </div>
        )}

        {isExtension && (
          <button
            className={`capability-card capability-toggle capability-privacy ${aiBlocked ? "is-on" : "is-off"}`}
            onClick={() => setBlockDialogOpen(true)}
            disabled={!aiBlockAvailable}
          >
            <span className="capability-card-icon">{Icons.aiBlock}</span>
            <span className="capability-card-label">{t.ai_block_title}</span>
            <span className="capability-state"><i aria-hidden="true" />{aiBlocked ? t.ai_block_enabled : t.feature_disabled}</span>
          </button>
        )}

        <button className="capability-card" onClick={() => navigateTo("quizlet")}>
          <span className="capability-card-icon">{Icons.quizlet}</span>
          <span className="capability-card-label">Quizlet</span>
        </button>

        <button className="capability-card capability-card-stats" onClick={() => navigateTo("statistics")}>
          <span className="capability-card-icon">{Icons.stats}</span>
          <span className="capability-card-label">{t.nav_stats}</span>
          <span className="capability-card-badge">{counts?.words ?? "…"}</span>
        </button>
        <button className="capability-card" onClick={() => navigateTo("settings", { settingsMode: "menu" })}>
          <span className="capability-card-icon">{Icons.settings}</span>
          <span className="capability-card-label">{t.nav_settings}</span>
        </button>
        <button className="capability-card capability-card-wide capability-card-alt" onClick={switchTargetLanguage} disabled={!settings || (settings.target_langs?.length ?? 1) < 2}>
          <span className="capability-card-icon">{Icons.language}</span>
          <span className="capability-card-badge">{targetLang.toUpperCase()}</span>
          <span className="capability-card-label">{LANGUAGES.find((lang) => lang.code === targetLang)?.name ?? targetLang}</span>
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
              {featureGuide === "reading_coach"
                ? Icons.readingCoach
                : featureGuide === "pattern_workshop"
                  ? Icons.grammar
                : featureGuide === "dual_subtitles"
                  ? Icons.dualSubtitles
                  : Icons.myWords}
            </span>
            <h2 id="feature-guide-title">
              {featureGuide === "reading_coach"
                ? t.reading_coach_guide_title
                : featureGuide === "pattern_workshop"
                  ? t.pattern_workshop_guide_title
                : featureGuide === "dual_subtitles"
                  ? t.dual_subtitles_guide_title
                  : t.my_words_title}
            </h2>
            <p className="feature-guide-intro">
              {featureGuide === "reading_coach"
                ? t.reading_coach_guide_intro
                : featureGuide === "pattern_workshop"
                  ? t.pattern_workshop_guide_intro
                : featureGuide === "dual_subtitles"
                  ? t.dual_subtitles_guide_intro
                  : t.my_words_intro}
            </p>
            <ol>
              {(featureGuide === "reading_coach"
                ? [t.reading_coach_guide_step_1, t.reading_coach_guide_step_2, t.reading_coach_guide_step_3]
                : featureGuide === "pattern_workshop"
                  ? [t.pattern_workshop_guide_step_1, t.pattern_workshop_guide_step_2, t.pattern_workshop_guide_step_3]
                : featureGuide === "dual_subtitles"
                  ? [t.dual_subtitles_guide_step_1, t.dual_subtitles_guide_step_2, t.dual_subtitles_guide_step_3]
                  : [t.my_words_guide_step_1, t.my_words_guide_step_2, t.my_words_guide_step_3]
              ).map((step, index) => <li key={index}>{step}</li>)}
            </ol>
            <p className="feature-guide-tip">
              {featureGuide === "reading_coach"
                ? t.reading_coach_guide_tip
                : featureGuide === "pattern_workshop"
                  ? t.pattern_workshop_guide_tip
                : featureGuide === "dual_subtitles"
                  ? t.dual_subtitles_guide_tip
                  : t.my_words_guide_tip}
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
