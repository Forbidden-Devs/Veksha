import { useT } from "./i18n";
import type { MicState } from "./useMicRecorder";

const MIC_ICON = (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8"  y1="23" x2="16" y2="23" />
  </svg>
);

const SPINNER_ICON = (
  <svg className="mic-btn-spinner" viewBox="0 0 24 24" width="16" height="16"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83
             M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
  </svg>
);

export function MicButton({
  state,
  volume,
  onClick,
  disabled = false,
}: {
  state: MicState;
  volume: number;
  onClick: () => void;
  disabled?: boolean;
}) {
  const t = useT();
  const isRec  = state === "recording";
  const isTx   = state === "transcribing";

  // Glow: hue stays indigo, saturation/lightness + shadow grow with volume
  const glowStyle = isRec
    ? {
        color: `hsl(239, ${50 + Math.round(volume * 50)}%, ${40 + Math.round(volume * 10)}%)`,
        boxShadow: `0 0 ${4 + Math.round(volume * 14)}px rgba(99,102,241,${0.25 + volume * 0.55})`,
      }
    : undefined;

  return (
    <button
      className={`mic-btn${isRec ? " mic-btn--rec" : ""}${isTx ? " mic-btn--tx" : ""}`}
      style={glowStyle}
      onClick={onClick}
      disabled={disabled || isTx}
      title={isRec ? t.mic_stop : isTx ? t.mic_recognizing : t.mic_voice_input}
      type="button"
    >
      {isTx ? SPINNER_ICON : MIC_ICON}
    </button>
  );
}
