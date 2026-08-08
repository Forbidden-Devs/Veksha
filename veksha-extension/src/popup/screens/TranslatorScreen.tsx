import { useEffect, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import { canSpeak, speakText } from "../../shared/speech";
import { useApp } from "../App";
import { appendTranscript, VoiceInputButton } from "../components/VoiceInputButton";

interface TranslationSheet {
  source: string;
  translated: string;
  speechLanguage: string;
  explanation: string;
}

const EMPTY_SHEET: TranslationSheet = {
  source: "",
  translated: "",
  speechLanguage: "",
  explanation: "",
};

export function TranslatorScreen() {
  const { username, openReminder, targetLang, nativeLang } = useApp();
  const t = useT();
  const [draft, setDraft] = useState("");
  const [sheet, setSheet] = useState(EMPTY_SHEET);
  const [working, setWorking] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [error, setError] = useState("");
  const isVoiceSetup = typeof location !== "undefined"
    && new URLSearchParams(location.search).get("voice_setup") === "1";

  async function translate() {
    const source = draft.trim();
    if (!source || working) return;
    setWorking(true);
    setError("");
    setSheet(EMPTY_SHEET);
    try {
      const response = await api.translate(
        source,
        nativeLang,
        targetLang,
        true,
      );
      setSheet({
        source,
        translated: response.translation,
        speechLanguage:
          response.detected_source_lang === targetLang ? nativeLang : targetLang,
        explanation: "",
      });
    } catch (reason) {
      setError((reason as Error).message || t.translator_failed);
    } finally {
      setWorking(false);
    }
  }

  async function explain() {
    if (!sheet.translated || explaining) return;
    setExplaining(true);
    try {
      const response = await api.explain(username, sheet.source, sheet.translated);
      setSheet((current) => ({ ...current, explanation: response.explanation }));
    } catch {
      setError(t.translator_explain_failed);
    } finally {
      setExplaining(false);
    }
  }

  function reset() {
    setDraft("");
    setSheet(EMPTY_SHEET);
    setError("");
  }

  return (
    <section className="screen translator-workbench">
      <div className="translator-toolbar">
        <span className="translator-route">{nativeLang.toUpperCase()} ⇄ {targetLang.toUpperCase()}</span>
        <RemindersButton username={username} onOpen={openReminder} />
      </div>

      {isVoiceSetup && (
        <p className="voice-input-setup" role="status">{t.voice_input_setup_hint}</p>
      )}

      <div className="translator-source">
        <label htmlFor="translator-draft">{t.translator_source_label}</label>
        <textarea
          id="translator-draft"
          value={draft}
          rows={5}
          maxLength={5000}
          placeholder={t.translator_source_placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void translate();
            }
          }}
        />
        <div className="translator-source-footer">
          <span>{draft.length}/5000</span>
          <div>
            <VoiceInputButton
              disabled={working}
              onTranscript={(text) => setDraft((current) => appendTranscript(current, text, 5000))}
            />
            {(draft || sheet.translated) && (
              <button type="button" className="translator-secondary" onClick={reset}>
                {t.translator_clear}
              </button>
            )}
            <button
              type="button"
              className="translator-run"
              disabled={!draft.trim() || working}
              onClick={() => void translate()}
            >
              {working ? t.translator_working : t.translator_action}
            </button>
          </div>
        </div>
      </div>

      {error && <p className="translator-error" role="alert">{error}</p>}

      {sheet.translated && (
        <article className="translation-sheet" aria-live="polite">
          <header>
            <span>{t.translator_result_label}</span>
            <div>
              {canSpeak() && (
                <button
                  type="button"
                  onClick={() => speakText(sheet.translated, sheet.speechLanguage)}
                >
                  {t.translator_listen}
                </button>
              )}
              {!sheet.explanation && (
                <button type="button" disabled={explaining} onClick={() => void explain()}>
                  {explaining ? t.translator_working : t.translator_explain}
                </button>
              )}
            </div>
          </header>
          <p className="translation-sheet-text">{sheet.translated}</p>
          {sheet.explanation && (
            <div className="translation-note">
              <strong>{t.translator_note_label}</strong>
              <p>{sheet.explanation}</p>
            </div>
          )}
        </article>
      )}
    </section>
  );
}

function RemindersButton({ username, onOpen }: { username: string; onOpen: () => void }) {
  const t = useT();
  const [hasDue, setHasDue] = useState(false);
  useEffect(() => {
    let active = true;
    void api.getReminders(username)
      .then(({ should_remind }) => { if (active) setHasDue(should_remind); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [username]);

  async function openIfNeeded() {
    try {
      const result = await api.getReminders(username);
      setHasDue(result.should_remind);
      if (result.should_remind) onOpen();
    } catch {
      // Reminders are optional; translation remains available when polling fails.
    }
  }

  return (
    <button
      type="button"
      className="translator-reminders"
      aria-label={t.reminder_label}
      onClick={() => void openIfNeeded()}
    >
      <span aria-hidden="true">◷</span>
      {hasDue && <i />}
    </button>
  );
}
