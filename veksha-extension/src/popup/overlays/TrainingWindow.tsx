import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { createSessionSocket, type SessionSocket } from "../../shared/wsProxy";
import { MicButton } from "../../shared/MicButton";
import { useMicRecorder } from "../../shared/useMicRecorder";
import type { TrainingOutcome, TrainingTask } from "../../shared/types";

type Phase = "loading" | "asking" | "checking" | "feedback" | "done" | "empty" | "error";

interface CheckResult {
  outcome: TrainingOutcome;
  feedback: string;
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

export function TrainingWindow({ username, onClose }: { username: string; onClose: () => void }) {
  const t = useT();
  const phaseRef = useRef<Phase>("loading");
  const [phase, _setPhase] = useState<Phase>("loading");
  function setPhase(p: Phase) { phaseRef.current = p; _setPhase(p); }

  const [currentTask, setCurrentTask] = useState<TrainingTask | null>(null);
  const [answer, setAnswer] = useState("");
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [progress, setProgress] = useState({ done: 0, target: 0 });
  const [errorMsg, setErrorMsg] = useState("");

  const wsRef = useRef<SessionSocket | null>(null);
  const queueRef = useRef<TrainingTask[]>([]);
  const wsExhaustedRef = useRef(false);
  const targetRef = useRef(0);
  const doneRef = useRef(0);
  const answerRef = useRef<HTMLTextAreaElement>(null);

  const [langs, setLangs] = useState<{ native: string; target: string }>({ native: "en", target: "en" });

  // The expected answer language depends on the task type, so we hint the STT
  // accordingly (Whisper mis-detects short, single-word answers otherwise):
  //   translation         → answer in the user's native language
  //   reverse_translation → answer in the target language (the word itself)
  //   synonym / example   → answer in the target language
  const recLang = !currentTask
    ? langs.target
    : currentTask.task_type === "translation"
    ? langs.native
    : langs.target;

  const mic = useMicRecorder((text) => { if (text) setAnswer(prev => (prev ? prev + " " : "") + text); }, recLang);

  useEffect(() => {
    init();
    api.getSettings(username)
      .then(s => setLangs({ native: s.native_lang || "en", target: s.target_lang || "en" }))
      .catch(() => {});
    return () => { wsRef.current?.close(); };
  }, []);

  async function init() {
    try {
      const { available_words } = await api.trainingInit(username);
      const target = Math.min(available_words, CONFIG.TRAINING_MAX_SESSION);
      targetRef.current = target;
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
        for (let i = 0; i < target; i++) {
          ws.send(JSON.stringify({ type: "request_task" }));
        }
      };

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string) as Record<string, unknown>;
        handleWsMessage(msg);
      };

      ws.onclose = () => { wsExhaustedRef.current = true; };

      ws.onerror = () => {
        if (phaseRef.current === "loading" && queueRef.current.length === 0) {
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
    if (msg.type === "task") {
      const task: TrainingTask = {
        task_id: msg.task_id as string,
        word: msg.word as string,
        context: (msg.context as string) ?? "",
        task_type: msg.task_type as TrainingTask["task_type"],
        question: msg.question as string,
        reverse_text: (msg.reverse_text as string | undefined) ?? undefined,
        counter: msg.counter as number | undefined,
      };
      queueRef.current.push(task);
      if (phaseRef.current === "loading") showNext();

    } else if (msg.type === "result") {
      const result: CheckResult = {
        outcome: msg.outcome as TrainingOutcome,
        feedback: msg.feedback as string,
      };
      setCheckResult(result);
      if (result.outcome !== "garbage") {
        const done = doneRef.current + 1;
        doneRef.current = done;
        setProgress(p => ({ ...p, done }));
        setPhase("feedback");
      } else {
        setPhase("asking");
      }

    } else if (msg.type === "done") {
      wsExhaustedRef.current = true;
      if (phaseRef.current === "loading") setPhase("done");

    } else if (msg.type === "error") {
      setPhase("error");
      setErrorMsg((msg.message as string) ?? t.training_err_server);
    }
  }

  function showNext() {
    const task = queueRef.current.shift();
    if (!task) {
      if (wsExhaustedRef.current || doneRef.current >= targetRef.current) {
        setPhase("done");
      } else {
        setPhase("loading");
      }
      return;
    }
    setCurrentTask(task);
    setAnswer("");
    setCheckResult(null);
    setPhase("asking");
    setTimeout(() => answerRef.current?.focus(), 50);
  }

  function submitAnswer() {
    if (!currentTask || !answer.trim() || phaseRef.current !== "asking") return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setPhase("error");
      setErrorMsg(t.training_err_lost);
      return;
    }
    ws.send(JSON.stringify({
      type: "answer",
      task_id: currentTask.task_id,
      word: currentTask.word,
      question: currentTask.question,
      answer: answer.trim(),
    }));
    setPhase("checking");
  }

  function handleNext() {
    if (doneRef.current >= targetRef.current) { setPhase("done"); return; }
    showNext();
  }

  function markKnown() {
    if (!currentTask) return;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "mark_known", word: currentTask.word }));
    }
    const newTarget = Math.max(0, targetRef.current - 1);
    targetRef.current = newTarget;
    setProgress(p => ({ ...p, target: newTarget }));
    showNext();
  }

  const pct = progress.target > 0 ? Math.round((progress.done / progress.target) * 100) : 0;
  const isAsking = phase === "asking";
  const isFeedback = phase === "feedback";
  const isChecking = phase === "checking";

  return (
    <div className="training-window">

      <div className="training-window-header" data-drag-handle>
        <div className="logo-badge logo-badge-sm">Ve</div>
        <span className="training-window-title">{t.training_title}</span>
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

      <div className="training-window-body">

        {phase === "loading" && (
          <p className="training-window-status">{t.training_loading}</p>
        )}

        {phase === "error" && (
          <p className="training-window-status training-window-error">{errorMsg}</p>
        )}

        {phase === "done" && (
          <>
            <p className="training-window-status">
              {t.training_done.replace("{n}", String(progress.done))}
            </p>
            <button className="btn btn-gradient btn-block" onClick={onClose}>{t.training_close}</button>
          </>
        )}

        {phase === "empty" && (
          <div className="training-empty">
            <div className="training-empty-icon">📚</div>
            <p className="training-window-status">{t.training_empty}</p>
            <button className="btn btn-gradient btn-block" onClick={onClose}>{t.training_close}</button>
          </div>
        )}

        {(isAsking || isChecking || isFeedback) && currentTask && (
          <>
            {currentTask.counter === -1 && (
              <span className="training-new-badge">{t.training_new_word}</span>
            )}

            <p
              className="training-prompt"
              dangerouslySetInnerHTML={{ __html: sanitize(currentTask.question) }}
            />

            {checkResult && (
              <div
                className={`training-feedback ${outcomeClass(checkResult.outcome)}`}
                dangerouslySetInnerHTML={{ __html: sanitize(checkResult.feedback) }}
              />
            )}

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
                    isFeedback ? handleNext() : submitAnswer();
                  }
                }}
                disabled={!isAsking || mic.state === "transcribing"}
              />
              <MicButton
                state={mic.state}
                volume={mic.volume}
                onClick={mic.toggle}
                disabled={!isAsking}
              />
              {mic.state === "transcribing" && (
                <div className="stt-overlay"><span className="stt-overlay-dot" /></div>
              )}
            </div>
            {mic.errorMsg && (
              <div className="stt-error-tip">{mic.errorMsg}</div>
            )}

            <button
              className="btn btn-gradient btn-block"
              onClick={isFeedback ? handleNext : submitAnswer}
              disabled={isChecking || (isAsking && !answer.trim())}
            >
              {isChecking ? t.training_checking : isFeedback ? t.training_next : t.training_check}
            </button>

            {currentTask.counter === -1 && isAsking && (
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
