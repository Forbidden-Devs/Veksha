import { useEffect, useMemo, useState } from "react";
import * as api from "../../shared/api";
import { MicButton } from "../../shared/MicButton";
import { useT } from "../../shared/i18n";
import { useMicRecorder } from "../../shared/useMicRecorder";
import type { WordEntry } from "../../shared/types";

export function AnkiCards({ username, words, nativeLang, targetLang, autoStartVoice, onClose }: {
  username: string;
  words: WordEntry[];
  nativeLang: string;
  targetLang: string;
  autoStartVoice?: boolean;
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
  const answerLang = card?.reverse ? targetLang : nativeLang;
  const mic = useMicRecorder((text) => setAnswer(text), answerLang, "dictionary_cards");

  useEffect(() => {
    if (!autoStartVoice) return;
    // Chrome may report the old permission state to an offscreen document for
    // a short moment after the permission window closes.
    const timer = window.setTimeout(() => mic.toggle(), 1500);
    return () => window.clearTimeout(timer);
  }, []);

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
        <input className="text-input" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder={t.training_placeholder} />
        <MicButton state={mic.state} volume={mic.volume} onClick={mic.toggle} disabled={mic.disabled} />
      </div>
      {mic.errorMsg && <div className="stt-error-tip">{mic.errorMsg}</div>}
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
