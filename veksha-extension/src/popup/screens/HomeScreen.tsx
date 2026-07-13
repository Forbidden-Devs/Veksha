import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { isExtension } from "../../shared/platform";
import type { SettingsData } from "../../shared/types";
import { useApp } from "../App";

/**
 * HomeScreen — Metro start screen: a tile grid plus the "ask or type" bar.
 *
 * Layout (mirrors the paper sketch):
 *   [assistant] [topics] [training] [immersion]
 *   [   words collected (wide, live)  ] [stats] [settings]
 *   [ ask-or-type input                       ] [send]
 */

const Icons = {
  dictionary: <svg viewBox="0 0 24 24"><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22V5.5Z"/><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22V5.5Z"/></svg>,
  topics: <svg viewBox="0 0 24 24"><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>,
  training: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m15 9 5-5M16 4h4v4"/></svg>,
  immersion: <svg viewBox="0 0 24 24"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/><circle cx="12" cy="12" r="3.5"/></svg>,
  stats: <svg viewBox="0 0 24 24"><path d="M5 20V10h4v10M10 20V4h4v16M15 20v-7h4v7M3 20h18"/></svg>,
  settings: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>,
  language: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3Z"/></svg>,
  send: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 2L11 13" />
      <path d="M22 2l-7 20-4-9-9-4z" />
    </svg>
  ),
};

export function HomeScreen() {
  const { username, navigateTo, openTraining, targetLang, nativeLang, setLangPair, sendToChat } = useApp();
  const t = useT();
  const [counts, setCounts] = useState<{ words: number; due: number } | null>(null);
  const [ask, setAsk] = useState("");
  const [settings, setSettings] = useState<SettingsData | null>(null);

  useEffect(() => {
    Promise.all([api.getKbSummary(username), api.getReminders(username)])
      .then(([kb, rem]) => setCounts({ words: kb.learning_count + kb.known_count, due: rem.due_words }))
      .catch(() => {});
  }, [username]);

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

  function submitAsk() {
    const text = ask.trim();
    if (!text) return;
    setAsk("");
    sendToChat(text);
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
          <button className="m-tile" onClick={() => navigateTo("immersion")}>
            <span className="m-tile-icon">{Icons.immersion}</span>
            <span className="m-tile-label">{t.nav_immersion}</span>
          </button>
        ) : <div className="m-tile m-tile-ghost" aria-hidden="true" />}

        <button className="m-tile m-tile-wide m-tile-stats" onClick={() => navigateTo("statistics")}>
          <span className="m-tile-icon">{Icons.stats}</span>
          <span className="m-tile-label">{t.nav_stats}</span>
          <span className="m-tile-badge">{counts?.words ?? "…"}</span>
        </button>
        <button className="m-tile" onClick={() => navigateTo("settings", { settingsMode: "menu" })}>
          <span className="m-tile-icon">{Icons.settings}</span>
          <span className="m-tile-label">{t.nav_settings}</span>
        </button>
        <button className="m-tile m-tile-alt" onClick={switchTargetLanguage} disabled={!settings || (settings.target_langs?.length ?? 1) < 2}>
          <span className="m-tile-icon">{Icons.language}</span>
          <span className="m-tile-badge">{targetLang.toUpperCase()}</span>
          <span className="m-tile-label">{LANGUAGES.find((lang) => lang.code === targetLang)?.name ?? targetLang}</span>
        </button>
      </div>

      <div className="m-ask">
        <input
          className="m-ask-input"
          type="text"
          placeholder={t.home_ask_placeholder}
          value={ask}
          onChange={(e) => setAsk(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submitAsk()}
        />
        <button className="m-ask-send" onClick={submitAsk} aria-label={t.chat_placeholder}>
          {Icons.send}
        </button>
      </div>
    </section>
  );
}
