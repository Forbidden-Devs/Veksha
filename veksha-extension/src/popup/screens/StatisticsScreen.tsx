import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { KBSummaryData, RemindersData, WordEntry } from "../../shared/types";
import { useApp } from "../App";

export function StatisticsScreen() {
  const { username, navigateTo } = useApp();
  const t = useT();
  const [summary, setSummary] = useState<KBSummaryData | null>(null);
  const [reminders, setReminders] = useState<RemindersData | null>(null);
  const [words, setWords] = useState<WordEntry[] | null>(null);
  const [statsError, setStatsError] = useState(false);

  useEffect(() => {
    Promise.all([api.getKbSummary(username), api.getReminders(username)])
      .then(([s, r]) => { setSummary(s); setReminders(r); })
      .catch(() => setStatsError(true));

    api.getKbWords(username)
      .then(w => setWords(w.words))
      .catch(() => setWords([]));
  }, [username]);

  function val(n: number | undefined) {
    if (statsError) return "–";
    if (n === undefined) return "...";
    return String(n);
  }

  function handleDelete(wordName: string) {
    setWords(prev => prev ? prev.filter(w => w.name !== wordName) : prev);
    api.deleteKbWord(username, wordName).catch(() => {
      api.getKbWords(username).then(w => setWords(w.words)).catch(() => {});
    });
  }

  function wordBadge(w: WordEntry) {
    if (w.known) return <span className="word-badge word-badge-known">{t.stats_badge_known}</span>;
    if (w.counter === -1) return <span className="word-badge word-badge-new">{t.stats_badge_new}</span>;
    return null;
  }

  function reviewLabel(w: WordEntry) {
    if (w.known || w.counter < 0 || !w.next_review) return null;
    const remainingMs = w.next_review * 1000 - Date.now();
    if (remainingMs < 0) return t.stats_review_overdue;
    const days = Math.ceil(remainingMs / 86_400_000);
    if (days === 0) return t.stats_review_today;
    return t.stats_review_in_days.replace("{n}", String(days));
  }

  return (
    <section className="screen screen-statistics">
      <header className="menu-header">
        <span className="menu-title">{t.stats_title}</span>
      </header>

      <div className="stats-cards">
        <div className="stat-card">
          <div className="stat-value">{val(summary?.learning_count)}</div>
          <div className="stat-label">{t.stats_in_progress}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{val(summary?.known_count)}</div>
          <div className="stat-label">{t.stats_known}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{val(summary?.topics_count)}</div>
          <div className="stat-label">{t.stats_topics}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{val(reminders?.due_words)}</div>
          <div className="stat-label">{t.stats_ready}</div>
        </div>
      </div>

      <div className="word-list-section">
        <div className="word-list-header">{t.stats_vocabulary}</div>
        <div className="word-list">
          {words === null && (
            <p className="word-list-placeholder">...</p>
          )}
          {words !== null && words.length === 0 && (
            <p className="word-list-placeholder">{t.topics_empty}</p>
          )}
          {words !== null && words.map(w => (
            <div key={w.name} className="word-list-item">
              <div className="word-list-primary">
                <div className="word-list-name">{w.name}</div>
                {reviewLabel(w) && <div className="word-list-review">{reviewLabel(w)}</div>}
              </div>
              <div className="word-list-meta">
                {w.context && <span className="word-list-context">{w.context}</span>}
                {wordBadge(w)}
                <button
                  className="word-delete-btn"
                  aria-label="Delete"
                  onClick={() => handleDelete(w.name)}
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
