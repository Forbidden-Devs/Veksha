import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { CONFIG } from "../../shared/config";
import { useT } from "../../shared/i18n";
import { createSessionSocket, type SessionSocket } from "../../shared/wsProxy";
import type { BlockContent, ContentSection, LessonBlock, TrainingOutcome } from "../../shared/types";

type Phase = "loading" | "ready" | "asking" | "checking" | "feedback" | "done" | "error";

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

function SectionView({ s }: { s: ContentSection }) {
  return (
    <div className={`lesson-section${s.highlight ? " lesson-section-hl" : ""}`}>
      <div className="lesson-section-header">
        {s.icon && <span className="lesson-section-icon">{s.icon}</span>}
        <strong>{s.header}</strong>
      </div>
      {s.items && s.items.length > 0 && (
        <ul className="lesson-section-items">
          {s.items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      )}
      {s.text && <p className="lesson-section-text">{s.text}</p>}
    </div>
  );
}

function BlockContentView({ content }: { content: BlockContent }) {
  return (
    <div className="lesson-block-content">
      <h2 className="lesson-block-title">{content.title}</h2>
      {content.intro && <p className="lesson-block-intro">{content.intro}</p>}
      {content.sections.map((s, i) => <SectionView key={i} s={s} />)}
    </div>
  );
}

export function LessonWindow({
  username,
  topicName,
  onClose,
}: {
  username: string;
  topicName: string;
  onClose: () => void;
}) {
  const t = useT();
  const phaseRef = useRef<Phase>("loading");
  const [phase, _setPhase] = useState<Phase>("loading");
  function setPhase(p: Phase) { phaseRef.current = p; _setPhase(p); }

  const [blocks, setBlocks] = useState<LessonBlock[]>([]);
  const [activeBlock, setActiveBlock] = useState(0);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [errorMsg, setErrorMsg] = useState("");

  const wsRef = useRef<SessionSocket | null>(null);
  const questionQueueRef = useRef<Array<{ question_id: string; block_name: string; question: string }>>([]);
  const currentQRef = useRef<{ question_id: string; block_name: string; question: string } | null>(null);
  const totalRef = useRef(0);
  const doneRef = useRef(0);
  const answerRef = useRef<HTMLTextAreaElement>(null);

  const tabsRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const overscrollRef = useRef(0);
  const overscrollResetTimer = useRef(0);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const wsBase = CONFIG.BACKEND_URL.replace(/^http/, "ws");
      const token = await api.getAuthToken();
      if (cancelled) return;
      const ws = createSessionSocket(`${wsBase}/api/lesson/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        // Auth must be the first message — the token never travels in the
        // URL (query strings leak into server/proxy logs).
        ws.send(JSON.stringify({ type: "auth", token }));
        ws.send(JSON.stringify({ type: "init", topic_name: topicName }));
      };

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data as string) as Record<string, unknown>;
        handleWsMessage(msg);
      };

      ws.onerror = () => {
        if (phaseRef.current === "loading") {
          setPhase("error");
          setErrorMsg(t.lesson_err_connect);
        }
      };
    })();

    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  function handleWsMessage(msg: Record<string, unknown>) {
    if (msg.type === "ready") {
      const blocksData = msg.blocks as LessonBlock[];
      const total = msg.total_questions as number;
      setBlocks(blocksData);
      totalRef.current = total;
      setProgress({ done: 0, total });
      setPhase("ready");
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        for (let i = 0; i < total; i++) {
          ws.send(JSON.stringify({ type: "request_question" }));
        }
      }

    } else if (msg.type === "question") {
      const q = {
        question_id: msg.question_id as string,
        block_name: msg.block_name as string,
        question: msg.question as string,
      };
      questionQueueRef.current.push(q);
      if (phaseRef.current === "ready" || (phaseRef.current === "asking" && !currentQRef.current)) {
        showNext();
      }

    } else if (msg.type === "result") {
      const outcome = msg.outcome as TrainingOutcome;
      setCheckResult({ outcome, feedback: msg.feedback as string });
      if (outcome !== "garbage") {
        const done = doneRef.current + 1;
        doneRef.current = done;
        setProgress(p => ({ ...p, done }));
        setPhase("feedback");
      } else {
        setPhase("asking");
      }

    } else if (msg.type === "done") {
      if (phaseRef.current === "feedback" || phaseRef.current === "ready") {
        setPhase("done");
      }

    } else if (msg.type === "error") {
      setPhase("error");
      setErrorMsg((msg.message as string) || t.lesson_err_server);
    }
  }

  function showNext() {
    const q = questionQueueRef.current.shift();
    if (!q) return;
    currentQRef.current = q;
    setQuestion(q.question);
    setAnswer("");
    setCheckResult(null);
    setPhase("asking");
    setTimeout(() => answerRef.current?.focus(), 50);
  }

  function submitAnswer() {
    if (!currentQRef.current || !answer.trim() || phaseRef.current !== "asking") return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setPhase("error"); setErrorMsg(t.lesson_err_lost);
      return;
    }
    ws.send(JSON.stringify({
      type: "answer",
      question_id: currentQRef.current.question_id,
      block_name: currentQRef.current.block_name,
      question: currentQRef.current.question,
      answer: answer.trim(),
    }));
    setPhase("checking");
  }

  function handleNext() {
    currentQRef.current = null;
    if (doneRef.current >= totalRef.current) { setPhase("done"); return; }
    if (questionQueueRef.current.length > 0) {
      showNext();
    } else {
      setPhase("ready");
    }
  }

  function goToBlock(index: number) {
    const clamped = Math.max(0, Math.min(blocks.length - 1, index));
    setActiveBlock(clamped);
    overscrollRef.current = 0;
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }

  // Keep the active tab in view and reset overscroll when the block changes.
  useEffect(() => {
    tabRefs.current[activeBlock]?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
    overscrollRef.current = 0;
  }, [activeBlock]);

  // "Scroll past the edge → switch block": once the content is pinned to the
  // bottom (or top), keep accumulating wheel intent in that direction; cross a
  // threshold and we move to the next (or previous) block. The accumulator is
  // signed and decays, so a stray flick — or a direction change — won't jump.
  function onContentWheel(e: React.WheelEvent<HTMLDivElement>) {
    const el = scrollRef.current;
    if (!el || e.deltaY === 0) return;

    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 2;
    const atTop = el.scrollTop <= 0;
    const canNext = e.deltaY > 0 && atBottom && activeBlock < blocks.length - 1;
    const canPrev = e.deltaY < 0 && atTop && activeBlock > 0;

    if (!canNext && !canPrev) { overscrollRef.current = 0; return; }

    // reset the accumulator if the wheel reversed direction
    if (Math.sign(overscrollRef.current) !== Math.sign(e.deltaY)) overscrollRef.current = 0;
    overscrollRef.current += e.deltaY;
    window.clearTimeout(overscrollResetTimer.current);
    overscrollResetTimer.current = window.setTimeout(() => { overscrollRef.current = 0; }, 400);

    if (overscrollRef.current > 220) {
      overscrollRef.current = 0;
      goToBlock(activeBlock + 1);
    } else if (overscrollRef.current < -220) {
      overscrollRef.current = 0;
      goToBlock(activeBlock - 1);
    }
  }

  const isAsking = phase === "asking";
  const isFeedback = phase === "feedback";
  const isChecking = phase === "checking";
  const showQA = isAsking || isChecking || isFeedback;
  const showBlocks = phase !== "loading" && phase !== "error" && phase !== "done";
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const blockPct = blocks.length > 0 ? Math.round(((activeBlock + 1) / blocks.length) * 100) : 0;

  return (
    <div className="lesson-overlay">

      <div className="lesson-header" data-drag-handle>
        <div className="logo-badge logo-badge-sm">Ve</div>
        <span className="lesson-header-title">{topicName}</span>
        <button className="icon-btn" style={{ marginLeft: "auto" }} aria-label="Close" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {phase === "loading" && (
        <div className="lesson-center">
          <p className="lesson-status">{t.lesson_preparing}</p>
        </div>
      )}

      {phase === "error" && (
        <div className="lesson-center">
          <p className="lesson-status lesson-status-error">{errorMsg}</p>
          <button className="btn btn-gradient" onClick={onClose}>{t.training_close}</button>
        </div>
      )}

      {phase === "done" && (
        <div className="lesson-center">
          <p className="lesson-status">
            {t.lesson_done.replace("{n}", String(progress.done))}
          </p>
          <button className="btn btn-gradient" onClick={onClose}>{t.training_close}</button>
        </div>
      )}

      {showBlocks && blocks.length > 0 && (
        <>
          {/* Block tabs — visible, numbered, jump anywhere */}
          <div className="lesson-tabs-row">
            <button
              className="lesson-tabs-arrow"
              aria-label="Previous block"
              disabled={activeBlock === 0}
              onClick={() => goToBlock(activeBlock - 1)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>

            <div className="lesson-tabs" ref={tabsRef}>
              {blocks.map((b, i) => (
                <button
                  key={i}
                  ref={el => { tabRefs.current[i] = el; }}
                  className={`lesson-tab${i === activeBlock ? " lesson-tab-active" : ""}`}
                  onClick={() => goToBlock(i)}
                  title={b.name}
                >
                  <span className="lesson-tab-num">{i + 1}</span>
                  <span className="lesson-tab-name">{b.name}</span>
                </button>
              ))}
            </div>

            <button
              className="lesson-tabs-arrow"
              aria-label="Next block"
              disabled={activeBlock === blocks.length - 1}
              onClick={() => goToBlock(activeBlock + 1)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          </div>

          {/* Where am I in the topic */}
          <div className="lesson-block-indicator">
            <span className="lesson-block-indicator-label">
              {t.lesson_block_of
                .replace("{n}", String(activeBlock + 1))
                .replace("{total}", String(blocks.length))}
            </span>
            <div className="lesson-block-indicator-track">
              <div className="lesson-block-indicator-fill" style={{ width: `${blockPct}%` }} />
            </div>
          </div>

          <div className="lesson-content-scroll" ref={scrollRef} onWheel={onContentWheel}>
            <div className="lesson-content-card">
              {blocks[activeBlock] && (
                <BlockContentView content={blocks[activeBlock].content} />
              )}
            </div>

            {activeBlock < blocks.length - 1 && (
              <div className="lesson-scroll-hint">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 9l6 6 6-6" />
                </svg>
                {t.lesson_scroll_next}
              </div>
            )}
          </div>

          {/* Practice — a separate panel, independent of block navigation */}
          <div className="lesson-practice-card">
            <div className="lesson-practice-head">
              <span className="lesson-practice-title">
                <span className="lesson-practice-icon">🎯</span>
                {t.lesson_practice}
              </span>
              <span className="lesson-practice-hint">{t.lesson_practice_hint} ✨</span>
            </div>

            <div className="lesson-practice-progress">
              <div className="training-progress-track" style={{ flex: 1 }}>
                <div className="training-progress-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="training-progress-label">{progress.done} / {progress.total}</span>
            </div>

            {phase === "ready" && (
              <p className="lesson-status" style={{ margin: "4px 0" }}>{t.lesson_loading_question}</p>
            )}

            {showQA && (
              <>
                <p
                  className="lesson-question"
                  dangerouslySetInnerHTML={{ __html: sanitize(question) }}
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
                    disabled={!isAsking}
                  />
                </div>

                <button
                  className="btn btn-gradient btn-block"
                  onClick={isFeedback ? handleNext : submitAnswer}
                  disabled={isChecking || (isAsking && !answer.trim())}
                >
                  {isChecking ? t.training_checking : isFeedback ? t.training_next : t.training_check}
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
