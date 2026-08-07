import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useI18n } from "../../shared/i18n";
import type { LearningGoalSummary, SettingsData } from "../../shared/types";
import { getLanguageName, getScriptName } from "../../shared/languages";
import { useApp } from "../App";

const MINUTE_CHOICES = [10, 15, 25];

export function LearningGoalsScreen() {
  const { username, openLesson } = useApp();
  const { t, lang } = useI18n();
  const [goals, setGoals] = useState<LearningGoalSummary[] | null>(null);
  const [draft, setDraft] = useState("");
  const [material, setMaterial] = useState("");
  const [showMaterial, setShowMaterial] = useState(false);
  const [minutes, setMinutes] = useState(MINUTE_CHOICES[1]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [alphabetCreating, setAlphabetCreating] = useState(false);

  useEffect(() => {
    Promise.all([api.getLearningGoals(username), api.getSettings(username)])
      .then(([response, loadedSettings]) => {
        setGoals(response.goals);
        setSettings(loadedSettings);
      })
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

  async function startAlphabetCourse() {
    const currentSettings = settings;
    const writing = currentSettings?.writing_system;
    if (!currentSettings || !writing?.course_available || alphabetCreating) return;
    const existing = goals?.find((goal) => goal.kind === "alphabet" && !goal.achieved);
    if (existing) {
      openLesson({ goalId: existing.goal_id }, existing.statement);
      return;
    }
    setAlphabetCreating(true);
    setError("");
    try {
      const statement = t.literacy_course_goal
        .replace("{language}", getLanguageName(currentSettings.target_lang, lang))
        .replace("{script}", getScriptName(writing.script, lang, writing.script_name));
      const created = await api.createLearningGoal(username, {
        statement,
        minutes: 15,
        kind: "alphabet",
      });
      openLesson({ goalId: created.goal_id }, created.statement);
    } catch {
      setError(t.literacy_course_failed);
      setAlphabetCreating(false);
    }
  }

  return (
    <section className="screen learning-goals">
      {settings?.writing_system?.course_available && (
        <aside className={`literacy-course literacy-course-${settings.writing_system.literacy_stage}`}>
          <div className="literacy-course-copy">
            <span className="goal-composer-kicker">{t.literacy_course_kicker}</span>
            <h2>{t.literacy_course_title}</h2>
            <p>
              {settings.writing_system.literacy_stage === "mastered"
                ? t.literacy_course_mastered
                : settings.writing_system.kind === "latin_extended"
                  ? t.literacy_course_latin_desc
                  : settings.writing_system.kind === "script_variant"
                  ? t.literacy_course_variant_desc
                  : t.literacy_course_new_desc}
            </p>
          </div>
          {settings.writing_system.literacy_stage !== "mastered" ? (
            <button type="button" disabled={alphabetCreating} onClick={() => void startAlphabetCourse()}>
              {alphabetCreating
                ? t.translator_working
                : settings.writing_system.literacy_stage === "learning"
                  ? t.literacy_course_continue
                  : t.literacy_course_start}
            </button>
          ) : (
            <span className="literacy-course-done">✓ {t.literacy_course_done}</span>
          )}
        </aside>
      )}
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
