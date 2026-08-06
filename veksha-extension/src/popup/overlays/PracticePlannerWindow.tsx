/**
 * PracticePlannerWindow — the Adaptive Practice Planner session surface.
 *
 * The server plans one exercise at a time (sense × skill × format), so this
 * window asks for a task only once the previous one is committed: prefetching
 * would hand out exercises chosen before the answers that shape them.
 *
 * An answer is graded in two steps. The server returns a verdict plus a
 * suggested FSRS rating; the learner can accept it or pick another of the four
 * before anything is scheduled. Listening tasks are voiced here — the backend
 * has no audio pipeline, so the client declares whether it can speak at all.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { canSpeak, speakText } from "../../shared/speech";
import { createSessionSocket, type SessionSocket } from "../../shared/wsProxy";
import type {
  FsrsRating,
  PracticeReason,
  PracticeSkill,
  SessionSummary,
  SkillProgress,
  TrainingOutcome,
  TrainingTask,
} from "../../shared/types";

type Phase =
  | "loading"
  | "asking"
  | "checking"
  | "feedback"
  | "done"
  | "empty"
  | "error";

const RATINGS: FsrsRating[] = ["again", "hard", "good", "easy"];

interface CheckResult {
  outcome: TrainingOutcome;
  feedback: string;
  errorNote: string;
  expectedAnswer: string;
  suggestedRating: FsrsRating | null;
}

function sanitize(text: string): string {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\r\n|\r|\n/g, "<br>");
}

function outcomeClass(outcome: TrainingOutcome): string {
  if (outcome === "correct") return "feedback-correct";
  if (outcome === "incorrect" || outcome === "garbage") return "feedback-incorrect";
  return "feedback-vague";
}

export function PracticePlannerWindow({
  username,
  onClose,
}: { username: string; onClose: () => void }) {
  const t = useT();
  const phaseRef = useRef<Phase>("loading");
  const [phase, _setPhase] = useState<Phase>("loading");
  function setPhase(p: Phase) { phaseRef.current = p; _setPhase(p); }

  const [task, setTask] = useState<TrainingTask | null>(null);
  const [answer, setAnswer] = useState("");
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [rating, setRating] = useState<FsrsRating | null>(null);
  const [hintShown, setHintShown] = useState(false);
  const [progress, setProgress] = useState({ done: 0, target: 0 });
  const [skills, setSkills] = useState<SkillProgress[]>([]);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const wsRef = useRef<SessionSocket | null>(null);
  const taskRef = useRef<TrainingTask | null>(null);
  const askedAtRef = useRef(0);
  const hintsUsedRef = useRef(0);
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const speechRef = useRef(false);
  const languageRef = useRef("en");

  const skillName = useCallback(
    (skill: PracticeSkill) => t[`practice_skill_${skill}`] ?? skill,
    [t],
  );

  const reasonText = useCallback(
    (reason: PracticeReason) =>
      (t[`practice_why_${reason.code}`] ?? "").replace(
        "{skill}",
        skillName(reason.skill),
      ),
    [t, skillName],
  );

  useEffect(() => {
    void init();
    return () => { wsRef.current?.close(); };
  }, []);

  async function init() {
    try {
      const [{ available_words, skills: initialSkills }, settings] = await Promise.all([
        api.trainingInit(username),
        api.getSettings(username).catch(() => null),
      ]);
      languageRef.current = settings?.target_lang || "en";
      speechRef.current = canSpeak();
      setSkills(initialSkills ?? []);

      const target = Math.min(available_words, CONFIG.TRAINING_MAX_SESSION);
      setProgress({ done: 0, target });
      if (target === 0) { setPhase("empty"); return; }

      const wsBase = CONFIG.BACKEND_URL.replace(/^http/, "ws");
      const token = await api.getAuthToken();
      const ws = createSessionSocket(`${wsBase}/api/training/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        // Auth must be the first message — the token never travels in the
        // URL (query strings leak into server/proxy logs).
        ws.send(JSON.stringify({ type: "auth", token }));
        ws.send(JSON.stringify({ type: "init", audio: speechRef.current }));
        ws.send(JSON.stringify({ type: "request_task" }));
      };

      ws.onmessage = (e) => {
        handleWsMessage(JSON.parse(e.data as string) as Record<string, unknown>);
      };

      ws.onerror = () => {
        if (phaseRef.current === "loading") {
          setPhase("error");
          setErrorMsg(t.training_err_connect);
        }
      };

    } catch (err) {
      setPhase("error");
      setErrorMsg(String(err));
    }
  }

  function handleWsMessage(msg: Record<string, unknown>) {
    if (msg.type === "session") {
      setProgress(p => ({ ...p, target: msg.target as number }));

    } else if (msg.type === "task") {
      showTask({
        task_id: msg.task_id as string,
        item_id: msg.item_id as string,
        task_kind: msg.task_kind as TrainingTask["task_kind"],
        skill: msg.skill as PracticeSkill,
        stage: msg.stage as TrainingTask["stage"],
        question: msg.question as string,
        options: (msg.options as string[]) ?? [],
        audio_text: (msg.audio_text as string) ?? "",
        hint: (msg.hint as string) ?? "",
        counter: msg.counter as number | undefined,
        reason: msg.reason as PracticeReason,
        is_correction: Boolean(msg.is_correction),
      });

    } else if (msg.type === "result") {
      const suggested = (msg.suggested_rating as FsrsRating | null) ?? null;
      setCheckResult({
        outcome: msg.outcome as TrainingOutcome,
        feedback: msg.feedback as string,
        errorNote: (msg.error_note as string) ?? "",
        expectedAnswer: (msg.expected_answer as string) ?? "",
        suggestedRating: suggested,
      });
      if (suggested === null) {
        // Not an answer at all — nothing was scheduled, let them try again.
        setPhase("asking");
        setTimeout(() => answerRef.current?.focus(), 50);
      } else {
        setRating(suggested);
        setPhase("feedback");
      }

    } else if (msg.type === "committed") {
      // Session-wide confidence per skill, so the progress row keeps one
      // meaning throughout; per-word profiles arrive with the summary.
      setSkills((msg.skills as SkillProgress[]) ?? []);
      const p = msg.progress as { done: number; target: number };
      setProgress({ done: p.done, target: p.target });
      requestTask();

    } else if (msg.type === "done") {
      setSummary(msg.summary as SessionSummary);
      setPhase("done");

    } else if (msg.type === "error") {
      setPhase("error");
      setErrorMsg((msg.message as string) ?? t.training_err_server);
    }
  }

  function showTask(next: TrainingTask) {
    taskRef.current = next;
    setTask(next);
    setAnswer("");
    setCheckResult(null);
    setRating(null);
    setHintShown(false);
    hintsUsedRef.current = 0;
    askedAtRef.current = Date.now();
    setPhase("asking");
    if (next.audio_text) speakText(next.audio_text, languageRef.current);
    setTimeout(() => answerRef.current?.focus(), 50);
  }

  function send(payload: Record<string, unknown>): boolean {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setPhase("error");
      setErrorMsg(t.training_err_lost);
      return false;
    }
    ws.send(JSON.stringify(payload));
    return true;
  }

  function requestTask() {
    setPhase("loading");
    send({ type: "request_task" });
  }

  function submitAnswer(value?: string) {
    const current = taskRef.current;
    const text = (value ?? answer).trim();
    if (!current || !text || phaseRef.current !== "asking") return;
    if (
      send({
        type: "answer",
        task_id: current.task_id,
        answer: text,
        response_seconds: (Date.now() - askedAtRef.current) / 1000,
        hints_used: hintsUsedRef.current,
      })
    ) {
      setAnswer(text);
      setPhase("checking");
    }
  }

  function commit() {
    const current = taskRef.current;
    if (!current || !rating) return;
    if (send({ type: "commit", task_id: current.task_id, rating })) {
      setPhase("checking");
    }
  }

  function revealHint() {
    hintsUsedRef.current += 1;
    setHintShown(true);
  }

  function markKnown() {
    const current = taskRef.current;
    if (!current) return;
    send({ type: "mark_known", item_id: current.item_id });
    setProgress(p => ({ ...p, target: Math.max(0, p.target - 1) }));
    requestTask();
  }

  const pct = progress.target > 0
    ? Math.round((progress.done / progress.target) * 100)
    : 0;
  const isAsking = phase === "asking";
  const isFeedback = phase === "feedback";
  const isChecking = phase === "checking";
  const isChoice = !!task && task.options.length > 0;

  return (
    <div className="training-window">

      <div className="training-window-header" data-drag-handle>
        <div className="logo-badge logo-badge-sm">Ve</div>
        <span className="training-window-title">{t.practice_title}</span>
        <button className="icon-btn" style={{ marginLeft: "auto" }} aria-label="Close" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {phase !== "empty" && phase !== "error" && (
        <div className="training-progress-row" style={{ padding: "8px 14px 0" }}>
          <div className="training-progress-track">
            <div className="training-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="training-progress-label">{progress.done} / {progress.target}</span>
        </div>
      )}

      {skills.length > 0 && phase !== "empty" && phase !== "error" && (
        <div className="practice-skillbar">
          {skills.map(skill => (
            <div className="practice-skillbar-item" key={skill.skill} title={skillName(skill.skill)}>
              <span className="practice-skillbar-name">{skillName(skill.skill)}</span>
              <div className="practice-skillbar-track">
                <div
                  className={`practice-skillbar-fill${skill.attempts === 0 ? " is-untested" : ""}`}
                  style={{ width: `${Math.round(skill.confidence * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="training-window-body">

        {phase === "loading" && (
          <p className="training-window-status">{t.practice_planning}</p>
        )}

        {phase === "error" && (
          <p className="training-window-status training-window-error">{errorMsg}</p>
        )}

        {phase === "done" && summary && (
          <SessionReport
            summary={summary}
            skillName={skillName}
            onClose={onClose}
          />
        )}

        {phase === "empty" && (
          <div className="training-empty">
            <div className="training-empty-icon">📚</div>
            <p className="training-window-status">{t.training_empty}</p>
            <button className="btn btn-gradient btn-block" onClick={onClose}>{t.training_close}</button>
          </div>
        )}

        {(isAsking || isChecking || isFeedback) && task && (
          <>
            <div className="practice-task-meta">
              <span className={`practice-skill-tag skill-${task.skill}`}>
                {t.practice_training_skill.replace("{skill}", skillName(task.skill))}
              </span>
              {task.counter === -1 && (
                <span className="training-new-badge">{t.training_new_word}</span>
              )}
              {task.is_correction && (
                <span className="practice-repair-tag">
                  {task.stage === "support" ? t.practice_stage_support : t.practice_stage_transfer}
                </span>
              )}
            </div>

            <p className="practice-why">{reasonText(task.reason)}</p>

            <p
              className="training-prompt"
              dangerouslySetInnerHTML={{ __html: sanitize(task.question) }}
            />

            {task.audio_text && (
              <button
                type="button"
                className="btn btn-ghost practice-replay"
                onClick={() => speakText(task.audio_text, languageRef.current)}
              >
                🔊 {t.practice_replay}
              </button>
            )}

            {checkResult && (
              <div className={`training-feedback practice-feedback ${outcomeClass(checkResult.outcome)}`}>
                <div
                  className="practice-feedback-text"
                  dangerouslySetInnerHTML={{ __html: sanitize(checkResult.feedback) }}
                />
                {checkResult.expectedAnswer && (
                  <div className="practice-expected">
                    {t.practice_expected_answer}: <strong>{checkResult.expectedAnswer}</strong>
                  </div>
                )}
                {checkResult.errorNote && (
                  <div className="practice-error-note">{checkResult.errorNote}</div>
                )}
              </div>
            )}

            {isChoice ? (
              <div className="practice-options">
                {task.options.map(option => (
                  <button
                    key={option}
                    type="button"
                    className={`btn btn-ghost practice-option${answer === option ? " is-chosen" : ""}`}
                    disabled={!isAsking}
                    onClick={() => submitAnswer(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            ) : (
              <div className="training-answer-area">
                <textarea
                  ref={answerRef}
                  className="textarea-input training-window-answer"
                  rows={2}
                  placeholder={isChecking ? t.training_checking : t.training_placeholder}
                  value={answer}
                  onChange={e => setAnswer(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (isFeedback) commit(); else submitAnswer();
                    }
                  }}
                  disabled={!isAsking}
                />
              </div>
            )}

            {isAsking && task.hint && !hintShown && (
              <button type="button" className="btn btn-ghost btn-block practice-hint-btn" onClick={revealHint}>
                💡 {t.practice_show_hint}
              </button>
            )}
            {hintShown && task.hint && (
              <div className="practice-hint">{task.hint}</div>
            )}

            {isFeedback && (
              <div className="practice-rating">
                <span className="practice-rating-label">{t.practice_rating_label}</span>
                <div className="practice-rating-row">
                  {RATINGS.map(value => (
                    <button
                      key={value}
                      type="button"
                      className={`btn practice-rating-btn rating-${value}${rating === value ? " is-selected" : ""}`}
                      onClick={() => setRating(value)}
                    >
                      {t[`practice_rating_${value}`]}
                    </button>
                  ))}
                </div>
                {checkResult?.suggestedRating && (
                  <span className="practice-rating-hint">
                    {t.practice_rating_suggested.replace(
                      "{rating}",
                      t[`practice_rating_${checkResult.suggestedRating}`],
                    )}
                  </span>
                )}
              </div>
            )}

            {!isChoice || isFeedback ? (
              <button
                className="btn btn-gradient btn-block"
                onClick={isFeedback ? commit : () => submitAnswer()}
                disabled={isChecking || (isAsking && !answer.trim())}
              >
                {isChecking ? t.training_checking : isFeedback ? t.training_next : t.training_check}
              </button>
            ) : null}

            {task.counter === -1 && isAsking && (
              <button className="btn btn-ghost btn-block" onClick={markKnown}>
                {t.training_already_know}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function SessionReport({
  summary,
  skillName,
  onClose,
}: {
  summary: SessionSummary;
  skillName: (skill: PracticeSkill) => string;
  onClose: () => void;
}) {
  const t = useT();
  const consolidated = summary.items.filter(item => item.consolidated);
  const shaky = summary.items.filter(item => !item.consolidated);

  return (
    <div className="practice-summary">
      <p className="training-window-status">
        {t.training_done.replace("{n}", String(summary.reviewed))}
      </p>

      {summary.corrections > 0 && (
        <p className="practice-summary-line">
          {t.practice_summary_corrections.replace("{n}", String(summary.corrections))}
        </p>
      )}

      {summary.skills.length > 0 && (
        <div className="practice-summary-skills">
          {summary.skills.map(entry => (
            <span key={entry.skill} className="practice-skill-tag">
              {skillName(entry.skill)} · {entry.count}
            </span>
          ))}
        </div>
      )}

      {consolidated.length > 0 && (
        <div className="practice-summary-block">
          <h4>{t.practice_summary_consolidated}</h4>
          <ul>
            {consolidated.map(item => (
              <li key={item.item_id}>
                <strong>{item.term}</strong>
                <span className="practice-summary-limit">
                  {t.practice_summary_limited_by.replace(
                    "{skill}",
                    skillName(item.limiting_skill),
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {shaky.length > 0 && (
        <div className="practice-summary-block">
          <h4>{t.practice_summary_needs_work}</h4>
          <ul>
            {shaky.map(item => (
              <li key={item.item_id}>
                <strong>{item.term}</strong>
                <span className="practice-summary-limit">
                  {t.practice_summary_limited_by.replace(
                    "{skill}",
                    skillName(item.limiting_skill),
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button className="btn btn-gradient btn-block" onClick={onClose}>
        {t.training_close}
      </button>
    </div>
  );
}
