import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { LearningGoalSummary } from "../../shared/types";
import { useApp } from "../App";

const MINUTE_CHOICES = [10, 15, 25];

export function LearningGoalsScreen() {
  const { username, openLesson } = useApp();
  const t = useT();
  const [goals, setGoals] = useState<LearningGoalSummary[] | null>(null);
  const [draft, setDraft] = useState("");
  const [material, setMaterial] = useState("");
  const [showMaterial, setShowMaterial] = useState(false);
  const [minutes, setMinutes] = useState(MINUTE_CHOICES[1]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getLearningGoals(username)
      .then((response) => setGoals(response.goals))
      .catch(() => setError(t.lesson_goals_load_failed));
  }, [t.lesson_goals_load_failed, username]);

  async function startGoal() {
    const statement = draft.trim();
    if (!statement || creating) return;
    setCreating(true);
    setError("");
    try {
      const created = await api.createLearningGoal(username, {
        statement,
        material: material.trim(),
        minutes,
      });
      openLesson({ goalId: created.goal_id }, created.statement);
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
            maxLength={200}
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

        <div className="goal-composer-options">
          <button
            type="button"
            className={`goal-composer-toggle${showMaterial ? " is-open" : ""}`}
            onClick={() => setShowMaterial((open) => !open)}
          >
            {showMaterial ? "− " : "+ "}{t.lesson_goals_material_toggle}
          </button>
          <label className="goal-composer-minutes">
            <span>{t.lesson_goals_minutes}</span>
            <select value={minutes} onChange={(event) => setMinutes(Number(event.target.value))}>
              {MINUTE_CHOICES.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>
        </div>

        {showMaterial && (
          <textarea
            className="goal-composer-material"
            rows={4}
            value={material}
            maxLength={20000}
            placeholder={t.lesson_goals_material_placeholder}
            onChange={(event) => setMaterial(event.target.value)}
          />
        )}

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
              const settled = goal.criteria.filter(
                (c) => c.status === "met" || c.status === "implied",
              ).length;
              return (
                <li key={goal.goal_id}>
                  <button
                    type="button"
                    onClick={() => openLesson({ goalId: goal.goal_id }, goal.statement)}
                  >
                    <span
                      className="goal-progress"
                      style={{ "--goal-progress": `${Math.round(goal.progress * 100)}%` } as React.CSSProperties}
                    >
                      <b>{Math.round(goal.progress * 100)}</b><small>%</small>
                    </span>
                    <span className="goal-copy">
                      <strong>{goal.statement}</strong>
                      <small>
                        {goal.framed
                          ? t.lesson_goals_evidence
                              .replace("{n}", String(settled))
                              .replace("{total}", String(goal.criteria.length))
                          : t.lesson_goals_continue}
                      </small>
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
