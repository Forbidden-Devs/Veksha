import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";
import type { WordEntry } from "../../shared/types";

export function AnkiCards({ username, words, onClose }: {
  username: string;
  words: WordEntry[];
  onClose: () => void;
}) {
  const t = useT();
  const cards = useMemo(() => [...words].sort(() => Math.random() - 0.5).map((word) => ({
    word,
    reverse: Math.random() > 0.5 && Boolean(word.translation),
  })), [words]);
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const card = cards[index];
  const inputRef = useRef<HTMLInputElement>(null);

  // Switching the OS keyboard layout can temporarily blur the page while the
  // DOM still reports this input as active. Remember that it owned the focus
  // before the window blur and restore the caret when the page becomes active.
  useEffect(() => {
    let shouldRestoreFocus = false;
    let frame = 0;

    const restoreFocus = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!shouldRestoreFocus || !document.hasFocus()) return;
        inputRef.current?.focus({ preventScroll: true });
        shouldRestoreFocus = false;
      });
    };
    const handleWindowBlur = () => {
      shouldRestoreFocus = document.activeElement === inputRef.current;
    };
    const handleWindowFocus = () => {
      if (shouldRestoreFocus) restoreFocus();
    };
    const handleFocusOut = (event: FocusEvent) => {
      if (event.target !== inputRef.current || event.relatedTarget) return;
      shouldRestoreFocus = true;
      restoreFocus();
    };
    const rescueTyping = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.key.length !== 1) return;
      const el = inputRef.current;
      if (!el || document.activeElement === el) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      el.focus({ preventScroll: true });
    };
    window.addEventListener("blur", handleWindowBlur);
    window.addEventListener("focus", handleWindowFocus);
    document.addEventListener("focusout", handleFocusOut);
    document.addEventListener("keydown", rescueTyping);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("blur", handleWindowBlur);
      window.removeEventListener("focus", handleWindowFocus);
      document.removeEventListener("focusout", handleFocusOut);
      document.removeEventListener("keydown", rescueTyping);
    };
  }, []);

  // Each new card starts with the caret ready in the answer field.
  useEffect(() => { inputRef.current?.focus(); }, [index]);

  function rate(rating: "again" | "good") {
    if (!card) return;
    api.reviewKbWord(username, card.word.name, rating).catch(() => {});
    setIndex((value) => value + 1);
    setAnswer("");
    setRevealed(false);
  }

  if (!card) {
    return <div className="anki-empty"><div>🎉</div><button className="btn btn-gradient" onClick={onClose}>{t.training_close}</button></div>;
  }

  const front = card.reverse ? card.word.translation : card.word.name;
  const back = card.reverse ? card.word.name : card.word.translation;

  return (
    <div className="anki-cards">
      <div className="anki-progress">{index + 1} / {cards.length}</div>
      <div className={`anki-card${revealed ? " anki-card-revealed" : ""}`}>
        <div className="anki-front">{front}</div>
        {revealed && <div className="anki-back">{back || "—"}{card.word.transcription && <small>{card.word.transcription}</small>}</div>}
      </div>
      <div className="anki-answer-row">
        <input
          ref={inputRef}
          className="text-input"
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") revealed ? rate("good") : setRevealed(true); }}
          placeholder={t.training_placeholder}
        />
      </div>
      {!revealed ? (
        <button className="btn btn-gradient" onClick={() => setRevealed(true)}>{t.dictionary_show_answer}</button>
      ) : (
        <div className="anki-rating">
          <button className="btn anki-again" onClick={() => rate("again")}>{t.dictionary_again}</button>
          <button className="btn anki-good" onClick={() => rate("good")}>{t.dictionary_good}</button>
        </div>
      )}
    </div>
  );
}
