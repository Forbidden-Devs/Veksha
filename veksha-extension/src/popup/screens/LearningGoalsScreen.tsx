import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { LessonTopicSummary } from "../../shared/types";
import { useApp } from "../App";

export function LearningGoalsScreen() {
  const { username, openLesson } = useApp();
  const t = useT();
  const [goals, setGoals] = useState<LessonTopicSummary[] | null>(null);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getLessonTopics(username)
      .then((response) => setGoals(response.topics))
      .catch(() => setError(t.lesson_goals_load_failed));
  }, [t.lesson_goals_load_failed, username]);

  async function startGoal() {
    const goal = draft.trim();
    if (!goal || creating) return;
    setCreating(true);
    setError("");
    try {
      await api.createLessonTopic(username, goal);
      openLesson(goal);
    } catch {
      setError(t.lesson_goals_create_failed);
      setCreating(false);
    }
  }

  return (
    <section className="screen learning-goals">
      <header className="goal-composer">
        <span className="goal-composer-kicker">{t.lesson_goals_kicker}</span>
        <h2>{t.lesson_goals_prompt}</h2>
        <p>{t.lesson_goals_hint}</p>
        <div className="goal-composer-row">
          <input
            value={draft}
            maxLength={120}
            placeholder={t.lesson_goals_placeholder}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void startGoal();
            }}
          />
          <button
            type="button"
            disabled={!draft.trim() || creating}
            onClick={() => void startGoal()}
          >
            {creating ? t.translator_working : t.lesson_goals_start}
          </button>
        </div>
        {error && <p className="goal-error" role="alert">{error}</p>}
      </header>

      <div className="goal-list-section">
        <div className="goal-list-heading">
          <h3>{t.lesson_goals_active}</h3>
          {goals && <span>{goals.length}</span>}
        </div>

        {goals === null && !error ? (
          <p className="goal-list-status">{t.lesson_goals_loading}</p>
        ) : goals?.length ? (
          <ol className="goal-list">
            {goals.map((goal) => {
              const progress = Math.round(goal.mastery * 100);
              return (
                <li key={goal.name}>
                  <button type="button" onClick={() => openLesson(goal.name)}>
                    <span className="goal-progress" style={{ "--goal-progress": `${progress}%` } as React.CSSProperties}>
                      <b>{progress}</b><small>%</small>
                    </span>
                    <span className="goal-copy">
                      <strong>{goal.name}</strong>
                      <small>{t.lesson_goals_evidence.replace("{n}", String(goal.block_count))}</small>
                    </span>
                    <span className="goal-next">{t.lesson_goals_continue} →</span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="goal-list-empty">
            <span aria-hidden="true">◎</span>
            <p>{t.lesson_goals_empty}</p>
          </div>
        )}
      </div>
    </section>
  );
}
