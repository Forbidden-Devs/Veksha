import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { Strings } from "../../shared/i18n/strings";
import type { RemindersData } from "../../shared/types";
import { useApp } from "../App";

function buildSubtitle(d: RemindersData, t: Strings): string {
  const parts: string[] = [];
  if (d.due_words > 0) parts.push(t.reminder_words.replace("{n}", String(d.due_words)));
  if (d.due_topic) parts.push(`${t.reminder_topic}: "${d.due_topic}"`);
  return parts.length
    ? t.reminder_have.replace("{items}", parts.join(" and "))
    : t.reminder_subtitle_default;
}

export function ReminderCard() {
  const { username, closeReminder, openTraining } = useApp();
  const t = useT();
  const [data, setData] = useState<RemindersData | null>(null);

  useEffect(() => {
    api.getReminders(username).then(setData).catch(() => {});
  }, [username]);

  function handleStartTraining() {
    closeReminder();
    openTraining();
  }

  return (
    <div className="overlay overlay-bottom" id="reminder-card">
      <div className="reminder-content">
        <div className="reminder-icon">&#128276;</div>
        <div className="reminder-text">
          <div className="reminder-title">{t.reminder_title} &#128170;</div>
          <div className="reminder-subtitle">
            {data ? buildSubtitle(data, t) : t.reminder_subtitle_default}
          </div>
        </div>
        <button className="icon-btn" aria-label="Dismiss" onClick={closeReminder}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <button className="btn btn-gradient btn-block" onClick={handleStartTraining}>
        {t.reminder_start}
      </button>
    </div>
  );
}
