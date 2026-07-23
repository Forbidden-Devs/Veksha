import { useState } from "react";
import { useT } from "../../shared/i18n";
import { assetUrl } from "../../shared/platform";

/**
 * TutorialWindow — the first-run walkthrough, shown as a big page overlay
 * (same mechanism as Training/Lesson). Each step shows a REAL component
 * replica (built from the same popup.css classes, scaled down inside a frame)
 * or a screenshot slot for things that only make sense on a live page
 * (the contextual translator, page immersion).
 */

const CloseX = () => (
  <button className="icon-btn" style={{ marginLeft: "auto" }} type="button">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  </button>
);

const SparkleIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
    <path d="M12 2l1.5 4.2L18 8l-4.5 1.8L12 14l-1.5-4.2L6 8l4.5-1.8z" />
    <path d="M18.5 13l.9 2.4 2.6 1-2.6 1-.9 2.6-.9-2.6-2.6-1 2.6-1z" />
  </svg>
);

// ---------------------------------------------------------------------------
// Faithful translator replica — reuses the real translation classes, non-interactive.
// ---------------------------------------------------------------------------

type Bubble = { role: "user" | "bot"; text: string; translation?: boolean };

function PhoneTranslator({ bubbles }: { bubbles: Bubble[] }) {
  const t = useT();
  return (
    <div className="tut-phone">
      <section className="screen screen-chat">
        <header className="chat-header">
          <strong className="translator-heading">{t.chat_mode_translate}</strong>
          <button className="immersion-toggle" type="button">
            <SparkleIcon />
            <span className="immersion-toggle-label">{t.immersion_off}</span>
          </button>
          <div className="header-actions">
            <button className="icon-btn" type="button">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </button>
            <button className="icon-btn" type="button">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
              </svg>
            </button>
          </div>
        </header>

        <div className="chat-messages">
          <div className="chat-day-divider"><span>{t.chat_today}</span></div>
          {bubbles.map((b, i) => (
            <div className="msg-group" key={i}>
              <div className={`msg msg-${b.role}`}><span>{b.text}</span></div>
              {b.translation && (
                <div className="msg-action-row">
                  <button className="msg-listen-btn" type="button"><span aria-hidden="true">🔊</span><span>{t.chat_listen}</span></button>
                  <button className="msg-explain-btn" type="button">{t.chat_explain} →</button>
                </div>
              )}
            </div>
          ))}
        </div>

        <form className="chat-input-row" onSubmit={(e) => e.preventDefault()}>
          <div className="chat-input-area">
            <textarea className="chat-input" rows={1} placeholder={t.chat_placeholder} readOnly />
          </div>
          <button type="button" className="send-btn">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M3 11.5L20.5 3 13 20.5l-2.2-7.3L3 11.5z" /></svg>
          </button>
        </form>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Training window replica — real .training-window classes, frozen mid-session.
// ---------------------------------------------------------------------------

function TrainingReplica() {
  const t = useT();
  return (
    <div className="tut-win-frame tut-frame-training">
      <div className="training-window">
        <div className="training-window-header">
          <div className="logo-badge logo-badge-sm">Ve</div>
          <span className="training-window-title">{t.training_title}</span>
          <CloseX />
        </div>
        <div className="training-progress-row" style={{ padding: "8px 14px 0" }}>
          <div className="training-progress-track"><div className="training-progress-fill" style={{ width: "40%" }} /></div>
          <span className="training-progress-label">4 / 10</span>
        </div>
        <div className="training-window-body">
          <p className="training-prompt">Translate the word <strong>“serendipity”</strong> in your own words.</p>
          <div className="training-feedback feedback-correct">Correct! A pleasant discovery made by chance. ✓</div>
          <div className="training-answer-area">
            <textarea className="textarea-input training-window-answer" rows={2} placeholder={t.training_placeholder} readOnly />
          </div>
          <button className="btn btn-gradient btn-block" type="button">{t.training_next}</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lesson window replica — real .lesson-overlay classes, block tabs + practice.
// ---------------------------------------------------------------------------

function LessonReplica() {
  const t = useT();
  const tabs = ["Intro", "In context", "Mistakes", "Forms", "Practice"];
  return (
    <div className="tut-win-frame tut-frame-lesson">
      <div className="lesson-overlay">
        <div className="lesson-header">
          <div className="logo-badge logo-badge-sm">Ve</div>
          <span className="lesson-header-title">Tenses</span>
          <CloseX />
        </div>

        <div className="lesson-tabs-row">
          <button className="lesson-tabs-arrow" type="button" disabled>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="lesson-tabs">
            {tabs.map((name, i) => (
              <button key={i} className={`lesson-tab${i === 0 ? " lesson-tab-active" : ""}`} type="button">
                <span className="lesson-tab-num">{i + 1}</span>
                <span className="lesson-tab-name">{name}</span>
              </button>
            ))}
          </div>
          <button className="lesson-tabs-arrow" type="button">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        </div>

        <div className="lesson-block-indicator">
          <span className="lesson-block-indicator-label">
            {t.lesson_block_of.replace("{n}", "1").replace("{total}", "5")}
          </span>
          <div className="lesson-block-indicator-track"><div className="lesson-block-indicator-fill" style={{ width: "20%" }} /></div>
        </div>

        <div className="lesson-content-scroll">
          <div className="lesson-content-card">
            <h2 className="lesson-block-title">Present vs. Past</h2>
            <p className="lesson-block-intro">How English marks time and why the tense often shifts compared to your language.</p>
            <div className="lesson-section lesson-section-hl">
              <div className="lesson-section-header"><span className="lesson-section-icon">💡</span><strong>Key idea</strong></div>
              <ul className="lesson-section-items">
                <li>Use Present Perfect for experience without a fixed time.</li>
                <li>Switch to Past Simple once a specific moment is named.</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="lesson-practice-card">
          <div className="lesson-practice-head">
            <span className="lesson-practice-title"><span className="lesson-practice-icon">🎯</span>{t.lesson_practice}</span>
            <span className="lesson-practice-hint">{t.lesson_practice_hint} ✨</span>
          </div>
          <p className="lesson-question">How would you say “I have lived here for 5 years”?</p>
          <div className="training-answer-area">
            <textarea className="textarea-input training-window-answer" rows={2} placeholder={t.training_placeholder} readOnly />
          </div>
          <button className="btn btn-gradient btn-block" type="button">{t.training_check}</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Screenshot slot — resolves through the extension origin (content-script
// context: a bare "/source" path would point at the host page, not us).
// ---------------------------------------------------------------------------

function Shot({ file, label }: { file: string; label: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="tut-shot tut-shot-missing">
        <span className="tut-shot-icon">🖼️</span>
        <span className="tut-shot-label">{label}</span>
      </div>
    );
  }
  return (
    <img
      className="tut-shot"
      src={assetUrl(`source/${file}`)}
      alt={label}
      onError={() => setFailed(true)}
    />
  );
}

/** Static "translate in place" illustration (a picture, not interactive): part
 *  of the text is shown swapped to the foreign language, with the original in a
 *  dark tooltip — app style, no copy icon. */
function ImmersionDemo() {
  return (
    <div className="tut-imm-demo">
      <p className="tut-imm-demo-text">
        En este sentido, es un campo genuinamente universal; además, la IA está{" "}
        <span className="tut-imm-hl">in constant evolution thanks to deep learning</span>, lo
        que acelera su capacidad.
      </p>
      <div className="tut-imm-tip">
        <span className="tut-imm-tip-tail" />
        en constante evolución gracias al aprendizaje profundo
      </div>
    </div>
  );
}

function ImmersionStage() {
  const t = useT();
  const points: Array<[string, string]> = [
    [t.tutorial_imm_p1_term, t.tutorial_imm_p1_desc],
    [t.tutorial_imm_p2_term, t.tutorial_imm_p2_desc],
    [t.tutorial_imm_p3_term, t.tutorial_imm_p3_desc],
    [t.tutorial_imm_p4_term, t.tutorial_imm_p4_desc],
  ];
  return (
    <div className="tut-immersion">
      <button className="immersion-toggle is-on tut-imm-toggle" type="button">
        <SparkleIcon />
        <span className="immersion-toggle-label">{t.immersion_on}</span>
      </button>
      <ImmersionDemo />
      <ul className="tut-imm-list">
        {points.map(([term, desc], i) => (
          <li key={i}>
            <span className="tut-u">{term}</span> — {desc}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Hero() {
  return (
    <div className="tut-hero">
      <div className="logo-badge tut-hero-logo">Ve</div>
      <div className="tut-hero-name">Veksha</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main window
// ---------------------------------------------------------------------------

export function TutorialWindow({ username: _username, onClose }: { username: string; onClose: () => void }) {
  const t = useT();
  const [step, setStep] = useState(0);

  const steps: Array<{ title: string; body: string; stage: React.ReactNode }> = [
    { title: t.tutorial_s1_title, body: t.tutorial_s1_body, stage: <Hero /> },
    {
      title: t.tutorial_s2_title,
      body: t.tutorial_s2_body,
      stage: (
        <div className="tut-shot-pair">
          <Shot file="tut_translator.png" label="Contextual translator on a page" />
          <Shot file="tut_translator_youtube.png" label="YouTube subtitle mode" />
        </div>
      ),
    },
    {
      title: t.tutorial_s4_title,
      body: t.tutorial_s4_body,
      stage: (
        <PhoneTranslator
          bubbles={[
            { role: "user", text: "serendipity" },
            { role: "bot", text: "счастливая случайность", translation: true },
          ]}
        />
      ),
    },
    { title: t.tutorial_train_title, body: t.tutorial_train_body, stage: <TrainingReplica /> },
    { title: t.tutorial_s8_title, body: t.tutorial_s8_body, stage: <LessonReplica /> },
    { title: t.tutorial_imm_title, body: t.tutorial_imm_lead, stage: <ImmersionStage /> },
    { title: t.tutorial_s7_title, body: t.tutorial_s7_body, stage: <Hero /> },
  ];

  const isLast = step === steps.length - 1;
  const isFirst = step === 0;
  const cur = steps[step];

  const next = () => (isLast ? onClose() : setStep((s) => s + 1));
  const back = () => setStep((s) => Math.max(0, s - 1));

  return (
    <div className="tut-window" data-tutorial-palette="forest">
      <div className="tut-header" data-drag-handle>
        <div className="logo-badge logo-badge-sm">Ve</div>
        <span className="tut-header-title">{t.help_body}</span>
        <button className="icon-btn" style={{ marginLeft: "auto" }} aria-label={t.training_close} onClick={onClose}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="tut-main">
        <div className="tut-stage">{cur.stage}</div>

        <div className="tut-footer">
          <h2 className="tut-title">{cur.title}</h2>
          <p className="tut-body">{cur.body}</p>

          <div className="tut-dots">
            {steps.map((_, i) => (
              <button
                key={i}
                className={`tut-dot${i === step ? " tut-dot-active" : ""}`}
                aria-label={`Step ${i + 1}`}
                onClick={() => setStep(i)}
              />
            ))}
          </div>

          <div className="tut-nav">
            {!isFirst ? (
              <button className="btn btn-ghost tut-back-btn" onClick={back}>{t.tutorial_back}</button>
            ) : (
              <span className="tut-nav-spacer" />
            )}
            <button className="btn btn-gradient tut-next-btn" onClick={next}>
              {isLast ? t.tutorial_start : t.tutorial_next}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
