import { useEffect, useMemo, useState } from "react";
import { getReminders } from "../../shared/api";
import { useI18n } from "../../shared/i18n";
import type { Strings } from "../../shared/i18n/strings";
import type { RemindersData } from "../../shared/types";
import { useApp } from "../App";

function buildSubtitle(d: RemindersData, t: Strings, locale: string): string {
  const wordReview = d.due_words > 0
    ? t.reminder_words.replace("{n}", String(d.due_words))
    : "";
  const goalReview = d.due_goal ? `${t.reminder_topic}: "${d.due_goal}"` : "";
  const due = [wordReview, goalReview].filter(Boolean);
  const items = new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(due);
  return due.length ? t.reminder_have.replace("{items}", items) : t.reminder_subtitle_default;
}

export function ReminderCard() {
  const { username, closeReminder, openTraining } = useApp();
  const { t, lang } = useI18n();
  const [data, setData] = useState<RemindersData | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getReminders(username)
      .then((response) => { if (!controller.signal.aborted) setData(response); })
      .catch(() => undefined);
    return () => controller.abort();
  }, [username]);

  const subtitle = useMemo(
    () => data ? buildSubtitle(data, t, lang) : t.reminder_subtitle_default,
    [data, lang, t],
  );

  function handleStartTraining() {
    closeReminder();
    openTraining();
  }

  return (
    <aside className="overlay overlay-bottom" id="reminder-card" aria-labelledby="practice-reminder-title">
      <p className="reminder-kicker">VEKSHA / {t.reminder_kicker}</p>
      <div className="reminder-content">
        <span className="reminder-icon" aria-hidden="true">V</span>
        <div className="reminder-text" aria-live="polite">
          <strong className="reminder-title" id="practice-reminder-title">{t.reminder_title}</strong>
          <p className="reminder-subtitle">{subtitle}</p>
        </div>
        <button className="icon-btn" aria-label={t.reminder_dismiss} onClick={closeReminder}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <button type="button" className="btn btn-gradient btn-block" onClick={handleStartTraining}>
        <span>{t.reminder_start}</span><span aria-hidden="true">↗</span>
      </button>
    </aside>
  );
}
