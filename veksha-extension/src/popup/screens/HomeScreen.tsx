import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { MicButton } from "../../shared/MicButton";
import { useMicRecorder } from "../../shared/useMicRecorder";
import { isExtension } from "../../shared/platform";
import type { SettingsData } from "../../shared/types";
import { useApp } from "../App";

/**
 * HomeScreen — Metro start screen: a tile grid plus the "ask or type" bar.
 *
 * Layout (mirrors the paper sketch):
 *   [assistant] [topics] [training] [immersion]
 *   [   words collected (wide, live)  ] [stats] [settings]
 *   [ ask-or-type input                       ] [mic|send]
 */

const Icons = {
  dictionary: "📖",
  topics: "📚",
  training: "🎯",
  immersion: "✨",
  stats: "📊",
  settings: "⚙️",
  language: "🌐",
  send: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 2L11 13" />
      <path d="M22 2l-7 20-4-9-9-4z" />
    </svg>
  ),
};

export function HomeScreen() {
  const { username, navigateTo, openTraining, targetLang, nativeLang, setLangPair, sendToChat, takeVoiceResume } = useApp();
  const t = useT();
  const [counts, setCounts] = useState<{ words: number; due: number } | null>(null);
  const [ask, setAsk] = useState("");
  const [settings, setSettings] = useState<SettingsData | null>(null);

  const mic = useMicRecorder((text) => {
    if (text) setAsk((prev) => (prev ? prev + " " : "") + text);
  }, targetLang, "home");

  useEffect(() => {
    if (takeVoiceResume() !== "home") return;
    const timer = window.setTimeout(() => mic.toggle(), 500);
    return () => window.clearTimeout(timer);
    // Resume is a one-shot value captured when the popup is recreated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

        <button className="m-tile m-tile-wide" onClick={() => navigateTo("statistics")}>
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
        <MicButton state={mic.state} volume={mic.volume} onClick={mic.toggle} disabled={mic.disabled} />
        <button className="m-ask-send" onClick={submitAsk} aria-label={t.chat_placeholder}>
          {Icons.send}
        </button>
      </div>
      {mic.errorMsg && <div className="chat-stt-error">{mic.errorMsg}</div>}
    </section>
  );
}
