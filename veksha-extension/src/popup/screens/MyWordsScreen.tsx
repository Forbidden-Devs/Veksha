import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import type { VocabularyInboxItem, VocabFrequencyEntry } from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { storageGet, storageSet } from "../../shared/platform";
import { useApp } from "../App";

function topDomain(domains: Record<string, number>): string {
  const entries = Object.entries(domains);
  if (!entries.length) return "";
  return entries.sort((a, b) => b[1] - a[1])[0][0];
}

export function MyWordsScreen() {
  const { username } = useApp();
  const t = useT();
  const [enabled, setEnabled] = useState(false);
  const [words, setWords] = useState<VocabFrequencyEntry[] | null>(null);
  const [addingWord, setAddingWord] = useState<string | null>(null);
  const [addedWords, setAddedWords] = useState<Set<string>>(() => new Set());
  const [addError, setAddError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<VocabularyInboxItem[] | null>(null);
  const [decidingItem, setDecidingItem] = useState<string | null>(null);
  const [inboxError, setInboxError] = useState(false);

  useEffect(() => {
    storageGet([CONFIG.STORAGE_KEY_VOCAB_FREQ]).then((result) => {
      setEnabled(Boolean(result[CONFIG.STORAGE_KEY_VOCAB_FREQ]));
    });
  }, []);

  useEffect(() => {
    api.getVocabFrequencyTop().then((result) => setWords(result.words)).catch(() => setWords([]));
    let active = true;
    const refreshInbox = () => {
      api.getVocabularyInbox()
        .then((result) => {
          if (active) setSuggestions(result.items);
        })
        .catch(() => {
          if (active) setSuggestions([]);
        });
    };
    refreshInbox();
    const timer = window.setInterval(refreshInbox, 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [enabled]);

  async function decideSuggestion(
    item: VocabularyInboxItem,
    decision: "learn" | "known" | "ignore",
  ) {
    if (decidingItem) return;
    setDecidingItem(item.item_id);
    setInboxError(false);
    try {
      await api.decideVocabularyInboxItem(item.item_id, decision);
      setSuggestions((current) => current?.filter((entry) => entry.item_id !== item.item_id) ?? []);
    } catch {
      setInboxError(true);
    } finally {
      setDecidingItem(null);
    }
  }

  async function toggle() {
    const next = !enabled;
    setEnabled(next);
    await storageSet({ [CONFIG.STORAGE_KEY_VOCAB_FREQ]: next });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_VOCAB_FREQ", enabled: next });
      }
    } catch {
      // Restricted pages cannot receive content-script messages; the saved
      // preference will still be applied on the next regular page.
    }
  }

  async function addToDictionary(word: string) {
    if (addingWord) return;
    setAddingWord(word);
    setAddError(null);
    try {
      await api.addKbWord(username, word);
      setAddedWords((current) => new Set(current).add(word));
    } catch {
      setAddError(word);
    } finally {
      setAddingWord(null);
    }
  }

  return (
    <section className="screen screen-statistics my-words-screen">
      <div className="vocabulary-inbox">
        <div className="vocabulary-inbox-heading">
          <h3>{t.vocabulary_inbox_title}</h3>
          {suggestions && suggestions.length > 0 && <span>{suggestions.length}</span>}
        </div>
        {inboxError && <p className="onboarding-error">{t.vocabulary_inbox_error}</p>}
        {suggestions === null && <p className="word-list-placeholder">…</p>}
        {suggestions?.length === 0 && (
          <p className="word-list-placeholder">{t.vocabulary_inbox_empty}</p>
        )}
        {suggestions?.map((item) => (
          <article className="vocabulary-inbox-item" key={item.item_id}>
            <div className="vocabulary-inbox-copy">
              <div className="vocabulary-inbox-term">
                <strong>{item.term}</strong>
                {item.transcription && <span>{item.transcription}</span>}
              </div>
              <div className="vocabulary-inbox-translation">{item.translation}</div>
              {item.latest_context && (
                <q className="vocabulary-inbox-context">{item.latest_context}</q>
              )}
              <small>
                {t.vocabulary_inbox_seen.replace("{n}", String(item.encounter_count))}
              </small>
            </div>
            <div className="vocabulary-inbox-actions">
              <button
                type="button"
                className="btn btn-gradient"
                disabled={decidingItem !== null}
                onClick={() => void decideSuggestion(item, "learn")}
              >
                {decidingItem === item.item_id ? "…" : t.vocabulary_inbox_learn}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={decidingItem !== null}
                onClick={() => void decideSuggestion(item, "known")}
              >
                {t.vocabulary_inbox_known}
              </button>
              <button
                type="button"
                className="vocabulary-inbox-ignore"
                disabled={decidingItem !== null}
                onClick={() => void decideSuggestion(item, "ignore")}
              >
                {t.vocabulary_inbox_ignore}
              </button>
            </div>
          </article>
        ))}
      </div>

      <div className="my-words-intro">
        <p>{t.my_words_intro}</p>
        <button
          className={`btn btn-block my-words-toggle${enabled ? " is-on" : ""}`}
          type="button"
          onClick={toggle}
          aria-pressed={enabled}
        >
          <span className="my-words-toggle-dot" aria-hidden="true" />
          {enabled ? t.my_words_on : t.my_words_off}
        </button>
      </div>

      <div className="word-list my-words-list">
        {addError && <p className="onboarding-error">{t.my_words_add_error}</p>}
        {words === null && <p className="word-list-placeholder">…</p>}
        {words?.length === 0 && <p className="word-list-placeholder">{t.my_words_empty}</p>}
        {words?.map((entry) => {
          const domain = topDomain(entry.domains);
          const isAdded = entry.in_dictionary || addedWords.has(entry.word);
          return (
            <div key={entry.word} className="word-list-item">
              <div className="my-words-word">
                <strong className="word-list-name">{entry.word}</strong>
                <span className="my-words-meta">
                  {t.my_words_seen_on.replace("{n}", String(entry.count)).replace("{domain}", domain)}
                </span>
              </div>
              <div className="my-words-actions">
                <span className={`my-words-badge ${entry.known ? "is-known" : "is-unknown"}`}>
                  {entry.known ? t.my_words_known : t.my_words_unknown}
                </span>
                <button
                  type="button"
                  className={`icon-btn my-words-add${isAdded ? " is-added" : ""}`}
                  onClick={() => void addToDictionary(entry.word)}
                  disabled={addingWord !== null || isAdded}
                  aria-label={isAdded
                    ? `${entry.word}: ${t.my_words_added}`
                    : `${entry.word}: ${t.my_words_add}`}
                  title={isAdded ? t.my_words_added : t.my_words_add}
                >
                  {addingWord === entry.word ? "…" : isAdded ? "✓" : "+"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
