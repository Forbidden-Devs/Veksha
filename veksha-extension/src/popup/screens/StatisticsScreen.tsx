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

  const cards = [
    [summary?.learning_count, t.stats_in_progress],
    [summary?.known_count, t.stats_known],
    [summary?.goals_count, t.stats_topics],
    [reminders?.due_words, t.stats_ready],
    [summary?.anki_reviews, t.stats_anki_reviews],
    [summary?.training_reviews, t.stats_training_reviews],
  ] as const;

  return (
    <section className="screen screen-statistics">
      <header className="menu-header">
        <span className="menu-title">{t.stats_title}</span>
      </header>

      <div className="stats-cards">
        {cards.map(([value, label]) => (
          <article className="stat-card" key={label}>
            <strong className="stat-value">{val(value)}</strong>
            <span className="stat-label">{label}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
