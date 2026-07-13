import { useMemo, useState } from "react";
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
