import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { speakText } from "../../shared/speech";
import type { WordEntry } from "../../shared/types";
import { useApp } from "../App";
import { AnkiCards } from "./AnkiCards";

export function DictionaryScreen() {
  const { username, targetLang, nativeLang, takeVoiceResume } = useApp();
  const t = useT();
  const [words, setWords] = useState<WordEntry[] | null>(null);
  const [cardsOpen, setCardsOpen] = useState(false);
  const [resumeVoice, setResumeVoice] = useState(false);

  useEffect(() => {
    api.getKbWords(username).then((result) => setWords(result.words)).catch(() => setWords([]));
  }, [username, targetLang]);

  useEffect(() => {
    if (takeVoiceResume() === "dictionary_cards") {
      setCardsOpen(true);
      setResumeVoice(true);
    }
  }, []);

  function remove(word: string) {
    setWords((current) => current?.filter((entry) => entry.name !== word) ?? current);
    api.deleteKbWord(username, word).catch(() => {
      api.getKbWords(username).then((result) => setWords(result.words)).catch(() => {});
    });
  }

  function enrich(word: WordEntry) {
    if (word.translation && word.transcription) return;
    api.getKbWordDetails(username, word.name).then((details) => {
      setWords((current) => current?.map((entry) => entry.name === details.name ? details : entry) ?? current);
    }).catch(() => {});
  }

  async function startCards() {
    if (!words?.length) return;
    const complete = await Promise.all(words.map((word) =>
      word.translation ? Promise.resolve(word) : api.getKbWordDetails(username, word.name).catch(() => word)
    ));
    setWords(complete);
    setCardsOpen(true);
  }

  if (cardsOpen && words) {
    return <section className="screen screen-statistics dictionary-screen"><AnkiCards username={username} words={words} nativeLang={nativeLang} targetLang={targetLang} autoStartVoice={resumeVoice} onClose={() => setCardsOpen(false)} /></section>;
  }

  return (
    <section className="screen screen-statistics dictionary-screen">
      <div className="dictionary-actions">
        <button className="btn btn-gradient" type="button" onClick={startCards} disabled={!words?.length}>🗂️ {t.dictionary_cards}</button>
      </div>
      <div className="word-list">
        {words === null && <p className="word-list-placeholder">…</p>}
        {words?.length === 0 && <p className="word-list-placeholder">{t.topics_empty}</p>}
        {words?.map((word) => {
          return (
            <div key={word.name} className="word-list-item dictionary-word" onClick={() => enrich(word)}>
              <strong className="word-list-name">{word.name}</strong>
              <span className="dictionary-inline-transcription">{word.transcription || "…"}</span>
              <span className="dictionary-row-translation">{word.translation || "…"}</span>
              <div className="dictionary-word-actions">
                <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); speakText(word.name, targetLang); }} aria-label={t.chat_listen}>🔊</button>
                <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); remove(word.name); }} aria-label="Delete">🗑️</button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
