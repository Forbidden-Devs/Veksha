import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { speakText } from "../../shared/speech";
import type { WordEntry } from "../../shared/types";
import { useApp } from "../App";
import { AnkiCards } from "./AnkiCards";

type DictionarySort = "az" | "za" | "newest" | "oldest";

const wordCollator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

export function DictionaryScreen() {
  const { username, targetLang } = useApp();
  const t = useT();
  const [words, setWords] = useState<WordEntry[] | null>(null);
  const [cardsOpen, setCardsOpen] = useState(false);
  const [selectedWord, setSelectedWord] = useState<string | null>(null);
  const [miningWord, setMiningWord] = useState<string | null>(null);
  const [miningError, setMiningError] = useState<string | null>(null);
  const [sort, setSort] = useState<DictionarySort>("az");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const miningRequest = useRef(0);

  useEffect(() => {
    api.getKbWords(username).then((result) => setWords(result.words)).catch(() => setWords([]));
  }, [username, targetLang]);

  const visibleWords = useMemo(() => {
    if (!words) return words;
    const query = searchQuery.trim().toLocaleLowerCase();
    const filtered = query
      ? words.filter((word) => word.name.toLocaleLowerCase().includes(query))
      : words;

    return [...filtered].sort((a, b) => {
      const alphabetical = wordCollator.compare(a.name, b.name);
      if (sort === "az") return alphabetical;
      if (sort === "za") return -alphabetical;
      const byDate = (a.added_at ?? 0) - (b.added_at ?? 0);
      return sort === "newest" ? -byDate || alphabetical : byDate || alphabetical;
    });
  }, [words, searchQuery, sort]);

  function updateSearch(value: string) {
    setSearchInput(value);
    const trimmed = value.trim();
    setSearchQuery(trimmed.length >= 3 ? trimmed : "");
  }

  function remove(itemId: string) {
    if (selectedWord === itemId) setSelectedWord(null);
    setWords((current) => current?.filter((entry) => entry.item_id !== itemId) ?? current);
    api.deleteKbWord(username, itemId).catch(() => {
      api.getKbWords(username).then((result) => setWords(result.words)).catch(() => {});
    });
  }

  function updateWord(updated: WordEntry) {
    setWords((current) => current?.map((entry) => entry.item_id === updated.item_id ? updated : entry) ?? current);
  }

  async function openMiningCard(word: WordEntry, force = false) {
    const request = ++miningRequest.current;
    setSelectedWord(word.item_id);
    setMiningWord(word.item_id);
    setMiningError(null);
    try {
      const details = await api.getKbWordDetails(username, word.item_id);
      updateWord(details);
      const mined = await api.mineKbWord(username, word.item_id, force);
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
      word.translation ? Promise.resolve(word) : api.getKbWordDetails(username, word.item_id).catch(() => word)
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
        <input
          className="dictionary-search"
          type="search"
          value={searchInput}
          placeholder={t.dictionary_search_placeholder}
          onChange={(event) => updateSearch(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              setSearchQuery(searchInput.trim());
            }
          }}
        />
        <select
          className="dictionary-sort"
          value={sort}
          onChange={(event) => setSort(event.target.value as DictionarySort)}
          aria-label={t.dictionary_sort_label}
          title={t.dictionary_sort_label}
        >
          <option value="az">{t.dictionary_sort_az}</option>
          <option value="za">{t.dictionary_sort_za}</option>
          <option value="newest">{t.dictionary_sort_newest}</option>
          <option value="oldest">{t.dictionary_sort_oldest}</option>
        </select>
        <button className="btn btn-gradient" type="button" onClick={startCards} disabled={!words?.length}>🗂️ {t.dictionary_cards}</button>
      </div>
      <div className="word-list">
        {words === null && <p className="word-list-placeholder">…</p>}
        {words?.length === 0 && <p className="word-list-placeholder">{t.dictionary_empty}</p>}
        {!!words?.length && visibleWords?.length === 0 && <p className="word-list-placeholder">{t.dictionary_no_results}</p>}
        {visibleWords?.map((word) => {
          const isSelected = selectedWord === word.item_id;
          return (
            <div key={word.item_id} className={`word-list-item dictionary-word-card${isSelected ? " is-open" : ""}`}>
              <div
                className="dictionary-word"
                onClick={() => isSelected ? setSelectedWord(null) : void openMiningCard(word)}
              >
                <strong className="word-list-name">{word.name}</strong>
                <span className="dictionary-inline-transcription">{word.transcription || "…"}</span>
                <span className="dictionary-row-translation">{word.translation || "…"}</span>
                <div className="dictionary-word-actions">
                  <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); void openMiningCard(word); }} aria-label={t.sentence_mining_title}>✨</button>
                  <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); speakText(word.name, targetLang); }} aria-label={t.translator_listen}>🔊</button>
                  <button type="button" className="icon-btn" onClick={(event) => { event.stopPropagation(); remove(word.item_id); }} aria-label="Delete">🗑️</button>
                </div>
              </div>
              {isSelected && (
                <div className="sentence-mining-card">
                  <div className="sentence-mining-header">
                    <strong>{t.sentence_mining_title}</strong>
                    {word.sentence_mining && miningWord !== word.item_id && (
                      <button type="button" onClick={() => void openMiningCard(word, true)}>
                        ↻ {t.sentence_mining_regenerate}
                      </button>
                    )}
                  </div>
                  {miningWord === word.item_id && <p className="sentence-mining-loading">✨ {t.sentence_mining_loading}</p>}
                  {miningError && miningWord !== word.item_id && <p className="onboarding-error">{miningError}</p>}
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
