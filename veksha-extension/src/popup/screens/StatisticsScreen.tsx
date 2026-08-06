import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { KBSummaryData, RemindersData } from "../../shared/types";
import { useApp } from "../App";

export function StatisticsScreen() {
  const { username } = useApp();
  const t = useT();
  const [summary, setSummary] = useState<KBSummaryData | null>(null);
  const [reminders, setReminders] = useState<RemindersData | null>(null);
  const [statsError, setStatsError] = useState(false);

  useEffect(() => {
    Promise.all([api.getKbSummary(username), api.getReminders(username)])
      .then(([s, r]) => { setSummary(s); setReminders(r); })
      .catch(() => setStatsError(true));

  }, [username]);

  function val(n: number | undefined) {
    if (statsError) return "–";
    if (n === undefined) return "...";
    return String(n);
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
          <div className="stat-value">{val(summary?.goals_count)}</div>
          <div className="stat-label">{t.stats_topics}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{val(reminders?.due_words)}</div>
          <div className="stat-label">{t.stats_ready}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{val(summary?.anki_reviews)}</div>
          <div className="stat-label">{t.stats_anki_reviews}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{val(summary?.training_reviews)}</div>
          <div className="stat-label">{t.stats_training_reviews}</div>
        </div>
      </div>

    </section>
  );
}
