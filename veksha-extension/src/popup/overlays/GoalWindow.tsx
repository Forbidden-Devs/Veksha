import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { createSessionSocket, type SessionSocket } from "../../shared/wsProxy";
import { OverlayHeader } from "../components/OverlayHeader";
import { RichText } from "../components/RichText";
import { feedbackTone } from "../components/trainingPresentation";
import { appendTranscript, VoiceInputButton } from "../components/VoiceInputButton";
import type {
  ActivityKind,
  ContentSection,
  CriterionStatus,
  CriterionView,
  DifficultyCause,
  GoalReport,
  GoalStep,
  StepMaterial,
  TrainingOutcome,
} from "../../shared/types";

type Phase = "framing" | "planning" | "asking" | "checking" | "feedback" | "summary" | "error";

// Keep lesson sockets active while the learner reads. Some proxies close an
// otherwise healthy WebSocket after roughly a minute of silence; reconnecting
// would initialize a fresh server session and replace the unanswered step.
const HEARTBEAT_INTERVAL_MS = 20_000;

interface StepResult {
  outcome: TrainingOutcome;
  cause: DifficultyCause;
  feedback: string;
}

/** How the goal is opened: by id when it already exists, by wording when new. */
export type GoalTarget = { goalId: string } | { statement: string; material?: string };

/** The socket speaks the server's field names, not the client's. */
function initPayload(target: GoalTarget): Record<string, unknown> {
  return "goalId" in target
    ? { type: "init", goal_id: target.goalId }
    : { type: "init", statement: target.statement, material: target.material ?? "" };
}

function SectionView({ section }: { section: ContentSection }) {
  return (
    <section className={`lesson-section${section.highlight ? " lesson-section-hl" : ""}`}>
      <h3 className="lesson-section-header">
        {section.icon && <span className="lesson-section-icon" aria-hidden="true">{section.icon}</span>}
        {section.header}
      </h3>
      {!!section.items?.length && (
        <ul className="lesson-section-items">
          {section.items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
      {section.text && <p className="lesson-section-text">{section.text}</p>}
    </section>
  );
}

function MaterialView({ material }: { material: StepMaterial }) {
  return (
    <div className="lesson-block-content">
      <h2 className="lesson-block-title">{material.title}</h2>
      {material.intro && <p className="lesson-block-intro">{material.intro}</p>}
      {material.sections.map((section, index) => (
        <SectionView key={`${index}:${section.header}`} section={section} />
      ))}
    </div>
  );
}

export function GoalWindow({
  username,
  target,
  title,
  onClose,
}: {
  username: string;
  target: GoalTarget;
  title?: string;
  onClose: () => void;
}) {
  const t = useT();
  const phaseRef = useRef<Phase>("framing");
  const [phase, _setPhase] = useState<Phase>("framing");
  function setPhase(p: Phase) { phaseRef.current = p; _setPhase(p); }

  const [statement, setStatement] = useState(title ?? "");
  const [criteria, setCriteria] = useState<CriterionView[]>([]);
  const [step, setStep] = useState<GoalStep | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<StepResult | null>(null);
  const [report, setReport] = useState<GoalReport | null>(null);
  const [budget, setBudget] = useState({ minutes: 0, spent: 0 });
  const [resumed, setResumed] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const wsRef = useRef<SessionSocket | null>(null);
  const stepRef = useRef<GoalStep | null>(null);
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempts = 0;
    const heartbeatTimer = setInterval(() => {
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_INTERVAL_MS);

    async function connect() {
      try {
        const wsBase = CONFIG.BACKEND_URL.replace(/^http/, "ws");
        const token = await api.getAuthToken();
        if (cancelled) return;
        const ws = createSessionSocket(`${wsBase}/api/learning-goals/ws`);
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled || wsRef.current !== ws) return;
          // Auth must be the first message — the token never travels in the
          // URL (query strings leak into server/proxy logs).
          ws.send(JSON.stringify({ type: "auth", token }));
          ws.send(JSON.stringify(initPayload(target)));
        };

        ws.onmessage = (e) => {
          if (cancelled || wsRef.current !== ws) return;
          reconnectAttempts = 0;
          try {
            handleWsMessage(JSON.parse(e.data as string) as Record<string, unknown>);
          } catch {
            setPhase("error");
            setErrorMsg(t.lesson_err_server);
          }
        };

        const recoverConnection = () => {
          if (cancelled || wsRef.current !== ws) return;
          wsRef.current = null;
          ws.close();
          if (phaseRef.current === "summary" || phaseRef.current === "error") return;
          if (reconnectAttempts >= 2) {
            setPhase("error");
            setErrorMsg(t.lesson_err_lost);
            return;
          }
          const delay = 400 * (2 ** reconnectAttempts);
          reconnectAttempts += 1;
          setPhase("planning");
          reconnectTimer = setTimeout(() => { void connect(); }, delay);
        };

        // Browsers commonly emit both events for one failure. Clearing wsRef
        // makes recovery idempotent for raw sockets and the Firefox proxy.
        ws.onclose = recoverConnection;
        ws.onerror = recoverConnection;
      } catch {
        if (cancelled) return;
        setPhase("error");
        setErrorMsg(t.lesson_err_connect);
      }
    }

    void connect();

    return () => {
      cancelled = true;
      clearInterval(heartbeatTimer);
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  function send(message: Record<string, unknown>): boolean {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setPhase("error");
      setErrorMsg(t.lesson_err_lost);
      return false;
    }
    ws.send(JSON.stringify(message));
    return true;
  }

  function handleWsMessage(msg: Record<string, unknown>) {
    if (msg.type === "goal") {
      setStatement(msg.statement as string);
      setCriteria(msg.criteria as CriterionView[]);
      setBudget({ minutes: msg.minutes as number, spent: msg.spent_seconds as number });
      setResumed(Boolean(msg.resumed));
      setPhase("planning");
      send({ type: "next_step" });

    } else if (msg.type === "step") {
      const next = msg as unknown as GoalStep;
      stepRef.current = next;
      setStep(next);
      setAnswer("");
      setResult(null);
      setPhase("asking");
      scrollRef.current?.scrollTo({ top: 0 });
      setTimeout(() => answerRef.current?.focus(), 50);

    } else if (msg.type === "result") {
      const outcome = msg.outcome as TrainingOutcome;
      setResult({
        outcome,
        cause: msg.cause as DifficultyCause,
        feedback: msg.feedback as string,
      });
      setCriteria(msg.criteria as CriterionView[]);
      setBudget(b => ({ ...b, spent: msg.spent_seconds as number }));
      // Off-task input leaves the step open, so the learner answers it again.
      setPhase(outcome === "garbage" ? "asking" : "feedback");

    } else if (msg.type === "summary") {
      setReport(msg as unknown as GoalReport);
      setPhase("summary");

    } else if (msg.type === "error") {
      setPhase("error");
      setErrorMsg((msg.message as string) || t.lesson_err_server);
    }
  }

  function submitAnswer() {
    if (!stepRef.current || !answer.trim() || phaseRef.current !== "asking") return;
    if (send({ type: "answer", step_id: stepRef.current.step_id, answer: answer.trim() })) {
      setPhase("checking");
    }
  }

  function nextStep() {
    setPhase("planning");
    send({ type: "next_step" });
  }

  function finishEarly() {
    setPhase("planning");
    send({ type: "finish" });
  }

  const isAsking = phase === "asking";
  const isChecking = phase === "checking";
  const isFeedback = phase === "feedback";
  const settled = criteria.filter(c => c.status === "met" || c.status === "implied").length;
  const minutesLeft = Math.max(0, Math.ceil(budget.minutes - budget.spent / 60));
  const activityLabel = step ? ACTIVITY_LABEL(t, step.activity) : "";
  const causeLabel = result && result.outcome !== "garbage" ? CAUSE_LABEL(t, result.cause) : "";
  const submitLabel = isChecking
    ? t.training_checking
    : isFeedback ? t.lesson_next_step : t.training_check;

  return (
    <section className="lesson-overlay" aria-label={statement}>

      <OverlayHeader
        headerClass="lesson-header"
        titleClass="lesson-header-title"
        title={statement}
        closeLabel={t.training_close}
        onClose={onClose}
      />

      {phase === "framing" && (
        <section className="lesson-center" aria-live="polite">
          <p className="lesson-status">{t.lesson_framing}</p>
        </section>
      )}

      {phase === "error" && (
        <section className="lesson-center" role="alert">
          <p className="lesson-status lesson-status-error">{errorMsg}</p>
          <button type="button" className="btn btn-gradient" onClick={onClose}>{t.training_close}</button>
        </section>
      )}

      {phase === "summary" && report && (
        <div className="lesson-content-scroll" ref={scrollRef}>
          <div className="lesson-content-card goal-report">
            <h2 className="lesson-block-title">
              {report.achieved
                ? t.lesson_summary_achieved
                : report.stopped_on_time
                  ? t.lesson_summary_out_of_time
                  : t.lesson_summary_stopped}
            </h2>
            {report.narrative && (
              <p className="lesson-block-intro"><RichText text={report.narrative} /></p>
            )}

            <ReportList title={t.lesson_summary_proven} entries={report.proven} t={t} />
            <ReportList title={t.lesson_summary_shaky} entries={report.shaky} t={t} />

            {report.examples.length > 0 && (
              <div className="lesson-section">
                <div className="lesson-section-header"><strong>{t.lesson_summary_examples}</strong></div>
                <ul className="lesson-section-items">
                  {report.examples.map((example, i) => <li key={i}>{example}</li>)}
                </ul>
              </div>
            )}

            {report.terms.length > 0 && (
              <div className="lesson-section">
                <div className="lesson-section-header"><strong>{t.lesson_summary_new_words}</strong></div>
                <ul className="lesson-section-items">
                  {report.terms.map((term, i) => (
                    <li key={i}>{term.term} — {term.translation}</li>
                  ))}
                </ul>
              </div>
            )}

            {report.patterns.length > 0 && (
              <div className="lesson-section">
                <div className="lesson-section-header"><strong>{t.lesson_summary_new_patterns}</strong></div>
                <ul className="lesson-section-items">
                  {report.patterns.map((pattern, i) => (
                    <li key={i}>{pattern.label} — {pattern.example}</li>
                  ))}
                </ul>
              </div>
            )}

            {report.next_goal && (
              <div className="lesson-section lesson-section-hl">
                <div className="lesson-section-header"><strong>{t.lesson_summary_next_goal}</strong></div>
                <p className="lesson-section-text">{report.next_goal}</p>
              </div>
            )}

            <button className="btn btn-gradient btn-block" onClick={onClose}>
              {t.training_close}
            </button>
          </div>
        </div>
      )}

      {(phase === "planning" || isAsking || isChecking || isFeedback) && criteria.length > 0 && (
        <>
          <div className="goal-criteria">
            <div className="goal-criteria-head">
              <span className="goal-criteria-title">{t.lesson_criteria_title}</span>
              <span className="goal-criteria-count">
                {t.lesson_criteria_done
                  .replace("{n}", String(settled))
                  .replace("{total}", String(criteria.length))}
                {" · "}
                {t.lesson_time_left.replace("{n}", String(minutesLeft))}
              </span>
            </div>
            <ol className="goal-criteria-list">
              {criteria.map((criterion) => (
                <li
                  key={criterion.criterion_id}
                  className={`goal-criterion status-${criterion.status}${
                    step?.criterion_id === criterion.criterion_id ? " is-active" : ""
                  }`}
                >
                  <span className="goal-criterion-mark" aria-hidden="true">
                    {criterion.status === "met" ? "✓" : criterion.status === "implied" ? "≈" : "•"}
                  </span>
                  <span className="goal-criterion-text">{criterion.statement}</span>
                  <span className="goal-criterion-status">{STATUS_LABEL(t, criterion.status)}</span>
                </li>
              ))}
            </ol>
            {resumed && <p className="goal-criteria-note">{t.lesson_resumed}</p>}
          </div>

          <div className="lesson-content-scroll" ref={scrollRef}>
            {step && (
              <div className="lesson-content-card">
                <span className="goal-activity-chip">{activityLabel}</span>
                <MaterialView material={step.material} />
              </div>
            )}
            {phase === "planning" && !step && (
              <p className="lesson-status" style={{ padding: "12px 0" }}>{t.lesson_loading_step}</p>
            )}
          </div>

          <div className="lesson-practice-card">
            <div className="lesson-practice-head">
              <span className="lesson-practice-title">
                <span className="lesson-practice-icon">🎯</span>
                {step?.criterion ?? ""}
              </span>
              <button className="goal-finish-btn" type="button" onClick={finishEarly}>
                {t.lesson_finish_early}
              </button>
            </div>

            {step && (
              <p className="lesson-question"><RichText text={step.question} /></p>
            )}

            {result && (
              <div className={`training-feedback ${feedbackTone(result.outcome)}`}>
                {causeLabel && <span className="goal-cause-chip">{causeLabel}</span>}
                <span><RichText text={result.feedback} /></span>
              </div>
            )}

            {step && (
              <>
                <div className="training-answer-area">
                  <textarea
                    ref={answerRef}
                    className="textarea-input training-window-answer"
                    rows={2}
                    placeholder={isChecking ? t.training_checking : t.lesson_practice_hint}
                    value={answer}
                    onChange={e => setAnswer(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        isFeedback ? nextStep() : submitAnswer();
                      }
                    }}
                    disabled={!isAsking}
                  />
                  <VoiceInputButton
                    disabled={!isAsking}
                    onTranscript={(text) => setAnswer((current) => appendTranscript(current, text, 5000))}
                  />
                </div>

                <button
                  type="button"
                  className="btn btn-gradient btn-block"
                  onClick={isFeedback ? nextStep : submitAnswer}
                  disabled={isChecking || (isAsking && !answer.trim())}
                >
                  {submitLabel}
                </button>
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function ReportList({
  title,
  entries,
  t,
}: {
  title: string;
  entries: GoalReport["proven"];
  t: ReturnType<typeof useT>;
}) {
  if (entries.length === 0) return null;
  return (
    <div className="lesson-section">
      <div className="lesson-section-header"><strong>{title}</strong></div>
      <ul className="lesson-section-items">
        {entries.map((entry) => (
          <li key={entry.criterion_id}>
            {entry.statement}
            <small className="goal-report-evidence">
              {" — "}
              {STATUS_LABEL(t, entry.status)}
              {entry.attempts > 0 && `, ${entry.attempts}×`}
            </small>
          </li>
        ))}
      </ul>
    </div>
  );
}

type T = ReturnType<typeof useT>;

function STATUS_LABEL(t: T, status: CriterionStatus): string {
  const labels: Record<CriterionStatus, string> = {
    untested: t.lesson_status_untested,
    gap: t.lesson_status_gap,
    emerging: t.lesson_status_emerging,
    implied: t.lesson_status_implied,
    met: t.lesson_status_met,
  };
  return labels[status];
}

function ACTIVITY_LABEL(t: T, activity: ActivityKind): string {
  const labels: Record<ActivityKind, string> = {
    find_in_material: t.lesson_activity_find_in_material,
    explain_example: t.lesson_activity_explain_example,
    compare_forms: t.lesson_activity_compare_forms,
    correct_error: t.lesson_activity_correct_error,
    predict_continuation: t.lesson_activity_predict_continuation,
    paraphrase: t.lesson_activity_paraphrase,
    create_example: t.lesson_activity_create_example,
    role_reply: t.lesson_activity_role_reply,
    apply_unaided: t.lesson_activity_apply_unaided,
  };
  return labels[activity] ?? "";
}

function CAUSE_LABEL(t: T, cause: DifficultyCause): string {
  const labels: Partial<Record<DifficultyCause, string>> = {
    unknown_term: t.lesson_cause_unknown_term,
    missed_signal: t.lesson_cause_missed_signal,
    rule_not_applied: t.lesson_cause_rule_not_applied,
    lucky_guess: t.lesson_cause_lucky_guess,
    explains_not_produces: t.lesson_cause_explains_not_produces,
    transfers_confidently: t.lesson_cause_transfers_confidently,
  };
  return labels[cause] ?? "";
}
