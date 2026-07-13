import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { speakText } from "../../shared/speech";
import type { WordEntry } from "../../shared/types";
import { useApp } from "../App";
import { AnkiCards } from "./AnkiCards";

export function DictionaryScreen() {
  const { username, targetLang } = useApp();
  const t = useT();
  const [words, setWords] = useState<WordEntry[] | null>(null);
  const [cardsOpen, setCardsOpen] = useState(false);
  const [selectedWord, setSelectedWord] = useState<string | null>(null);
  const [miningWord, setMiningWord] = useState<string | null>(null);
  const [miningError, setMiningError] = useState<string | null>(null);
  const miningRequest = useRef(0);

  useEffect(() => {
    api.getKbWords(username).then((result) => setWords(result.words)).catch(() => setWords([]));
  }, [username, targetLang]);

  function remove(word: string) {
    if (selectedWord === word) setSelectedWord(null);
    setWords((current) => current?.filter((entry) => entry.name !== word) ?? current);
    api.deleteKbWord(username, word).catch(() => {
      api.getKbWords(username).then((result) => setWords(result.words)).catch(() => {});
    });
  }

  function updateWord(updated: WordEntry) {
    setWords((current) => current?.map((entry) => entry.name === updated.name ? updated : entry) ?? current);
  }

  async function openMiningCard(word: WordEntry, force = false) {
    const request = ++miningRequest.current;
    setSelectedWord(word.name);
    setMiningWord(word.name);
    setMiningError(null);
    try {
      const details = await api.getKbWordDetails(username, word.name);
      updateWord(details);
      const mined = await api.mineKbWord(username, word.name, force);
      updateWord(mined);
    } catch {
      if (request === miningRequest.current) setMiningError(t.sentence_mining_error);
    } finally {
      if (request === miningRequest.current) setMiningWord(null);
    }
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
    return <section className="screen screen-statistics dictionary-screen"><AnkiCards username={username} words={words} onClose={() => setCardsOpen(false)} /></section>;
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
          const isSelected = selectedWord === word.name;
          return (
            <div key={word.name} className={`word-list-item dictionary-word-card${isSelected ? " is-open" : ""}`}>
              <div
                className="dictionary-word"
                onClick={() => isSelected ? setSelectedWord(null) : void openMiningCard(word)}
              >
                <strong className="word-list-name">{word.name}</strong>
                <span className="dictionary-inline-transcription">{word.transcription || "…"}</span>
                <span className="dictionary-row-translation">{word.translation || "…"}</span>
                <div className="dictionary-word-actions">
                  <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); void openMiningCard(word); }} aria-label={t.sentence_mining_title}>✨</button>
                  <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); speakText(word.name, targetLang); }} aria-label={t.chat_listen}>🔊</button>
                  <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); remove(word.name); }} aria-label="Delete">🗑️</button>
                </div>
              </div>
              {isSelected && (
                <div className="sentence-mining-card">
                  <div className="sentence-mining-header">
                    <strong>{t.sentence_mining_title}</strong>
                    {word.sentence_mining && miningWord !== word.name && (
                      <button type="button" onClick={() => void openMiningCard(word, true)}>
                        ↻ {t.sentence_mining_regenerate}
                      </button>
                    )}
                  </div>
                  {miningWord === word.name && <p className="sentence-mining-loading">✨ {t.sentence_mining_loading}</p>}
                  {miningError && miningWord !== word.name && <p className="onboarding-error">{miningError}</p>}
                  {word.sentence_mining && (
                    <>
                      <section>
                        <h4>{t.sentence_mining_examples}</h4>
                        <div className="sentence-mining-examples">
                          {word.sentence_mining.examples.map((example, index) => (
                            <div className="sentence-mining-example" key={`${example.sentence}-${index}`}>
                              <div>
                                <span className="sentence-mining-level">{example.level}</span>
                                {example.is_higher && <span className="sentence-mining-up">↑ {t.sentence_mining_level_up}</span>}
                              </div>
                              <strong>{example.sentence}</strong>
                              <span>{example.translation}</span>
                            </div>
                          ))}
                        </div>
                      </section>
                      {word.sentence_mining.mnemonic && (
                        <section className="sentence-mining-mnemonic">
                          <h4>{t.sentence_mining_mnemonic}</h4>
                          <p>💡 {word.sentence_mining.mnemonic}</p>
                        </section>
                      )}
                      <section>
                        <h4>{t.sentence_mining_collocations}</h4>
                        <div className="sentence-mining-collocations">
                          {word.sentence_mining.collocations.map((collocation) => (
                            <span key={collocation.text}>
                              <strong>{collocation.text}</strong>
                              {collocation.translation && <> · {collocation.translation}</>}
                            </span>
                          ))}
                        </div>
                      </section>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
