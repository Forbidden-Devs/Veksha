import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import type { VocabFrequencyEntry } from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { storageGet, storageSet } from "../../shared/platform";

function topDomain(domains: Record<string, number>): string {
  const entries = Object.entries(domains);
  if (!entries.length) return "";
  return entries.sort((a, b) => b[1] - a[1])[0][0];
}

export function MyWordsScreen() {
  const t = useT();
  const [enabled, setEnabled] = useState(false);
  const [words, setWords] = useState<VocabFrequencyEntry[] | null>(null);

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

  return (
    <section className="screen screen-statistics my-words-screen">
      <h2 className="lang-pick-title">{t.my_words_title}</h2>
      <p className="imm-modal-sub">{t.my_words_intro}</p>

      <button className="btn btn-gradient btn-block" type="button" onClick={toggle}>
        {enabled ? t.my_words_on : t.my_words_off}
      </button>

      <div className="word-list">
        {words === null && <p className="word-list-placeholder">…</p>}
        {words?.length === 0 && <p className="word-list-placeholder">{t.my_words_empty}</p>}
        {words?.map((entry) => {
          const domain = topDomain(entry.domains);
          return (
            <div key={entry.word} className="word-list-item">
              <strong className="word-list-name">{entry.word}</strong>
              <span className="dictionary-row-translation">
                {t.my_words_seen_on.replace("{n}", String(entry.count)).replace("{domain}", domain)}
              </span>
              <span className={`my-words-badge ${entry.known ? "is-known" : "is-unknown"}`}>
                {entry.known ? t.my_words_known : t.my_words_unknown}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
