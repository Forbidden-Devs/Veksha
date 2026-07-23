import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import type { VocabFrequencyEntry } from "../../shared/api";
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

  useEffect(() => {
    storageGet([CONFIG.STORAGE_KEY_VOCAB_FREQ]).then((result) => {
      setEnabled(Boolean(result[CONFIG.STORAGE_KEY_VOCAB_FREQ]));
    });
  }, []);

  useEffect(() => {
    api.getVocabFrequencyTop().then((result) => setWords(result.words)).catch(() => setWords([]));
  }, [enabled]);

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
      <h2 className="lang-pick-title">{t.my_words_title}</h2>
      <p className="imm-modal-sub">{t.my_words_intro}</p>

      <button className="btn btn-gradient btn-block" type="button" onClick={toggle}>
        {enabled ? t.my_words_on : t.my_words_off}
      </button>

      <div className="word-list">
        {addError && <p className="onboarding-error">{t.my_words_add_error}</p>}
        {words === null && <p className="word-list-placeholder">…</p>}
        {words?.length === 0 && <p className="word-list-placeholder">{t.my_words_empty}</p>}
        {words?.map((entry) => {
          const domain = topDomain(entry.domains);
          const isAdded = entry.in_dictionary || addedWords.has(entry.word);
          return (
            <div key={entry.word} className="word-list-item">
              <strong className="word-list-name">{entry.word}</strong>
              <span className="dictionary-row-translation">
                {t.my_words_seen_on.replace("{n}", String(entry.count)).replace("{domain}", domain)}
              </span>
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
          );
        })}
      </div>
    </section>
  );
}
