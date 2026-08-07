import { useEffect, useState } from "react";
import type { TranscriptionMode } from "../../shared/types";
import { useT } from "../../shared/i18n";

export function TranscriptionHint({
  text,
  mode = "standard",
  className = "",
}: {
  text: string;
  mode?: TranscriptionMode;
  className?: string;
}) {
  const t = useT();
  const [revealed, setRevealed] = useState(false);

  useEffect(() => setRevealed(false), [text, mode]);
  if (!text) return null;

  const classes = ["transcription-hint", className].filter(Boolean).join(" ");
  if (mode !== "on_demand" || revealed) {
    return (
      <span className={classes}>
        {text}
        {mode === "on_demand" && (
          <button
            type="button"
            className="transcription-hint-toggle"
            aria-label={t.transcription_hide}
            onClick={(event) => { event.stopPropagation(); setRevealed(false); }}
          >×</button>
        )}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={`${classes} transcription-hint-reveal`}
      aria-label={t.transcription_show}
      title={t.transcription_show}
      onClick={(event) => { event.stopPropagation(); setRevealed(true); }}
    >Aa</button>
  );
}
