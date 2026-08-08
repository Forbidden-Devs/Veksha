import { useEffect, useRef, useState } from "react";
import { useT } from "../../shared/i18n";
import {
  startVoiceRecording,
  transcribeRecording,
  type VoiceRecording,
} from "../../shared/voiceInput";

type State = "idle" | "starting" | "recording" | "processing";

function needsFirefoxPermissionTab(): boolean {
  return typeof location !== "undefined"
    && location.protocol === "moz-extension:"
    && new URLSearchParams(location.search).get("voice_setup") !== "1";
}

async function hasMicrophonePermission(): Promise<boolean> {
  try {
    const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
    return status.state === "granted";
  } catch {
    return false;
  }
}

async function openFirefoxPermissionTab(): Promise<void> {
  const url = chrome.runtime.getURL("src/popup/index.html?open=translator&voice_setup=1");
  await chrome.tabs.create({ url });
  window.close();
}

export function appendTranscript(current: string, transcript: string, maxLength: number): string {
  return [current.trimEnd(), transcript].filter(Boolean).join(current.trim() ? " " : "").slice(0, maxLength);
}

export function VoiceInputButton({
  onTranscript,
  language,
  disabled = false,
}: {
  onTranscript: (text: string) => void;
  language?: string;
  disabled?: boolean;
}) {
  const t = useT();
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState("");
  const recordingRef = useRef<VoiceRecording | null>(null);

  useEffect(() => () => { void recordingRef.current?.cancel(); }, []);

  async function stop() {
    const recording = recordingRef.current;
    if (!recording) return;
    recordingRef.current = null;
    setState("processing");
    try {
      const transcript = await transcribeRecording(await recording.stop(), language);
      if (!transcript) throw new Error("empty_transcript");
      onTranscript(transcript);
      setError("");
    } catch {
      setError(t.voice_input_failed);
    } finally {
      setState("idle");
    }
  }

  async function toggle() {
    if (state === "recording") {
      await stop();
      return;
    }
    if (state !== "idle") return;
    if (needsFirefoxPermissionTab() && !(await hasMicrophonePermission())) {
      try {
        await openFirefoxPermissionTab();
      } catch {
        setError(t.voice_input_denied);
      }
      return;
    }
    setState("starting");
    setError("");
    try {
      recordingRef.current = await startVoiceRecording(() => { void stop(); });
      setState("recording");
    } catch {
      setState("idle");
      setError(t.voice_input_denied);
    }
  }

  const label = state === "recording"
    ? t.voice_input_stop
    : state === "processing"
      ? t.voice_input_processing
      : t.voice_input_start;
  return (
    <span className="voice-input-wrap">
      <button
        type="button"
        className={`voice-input-button${state === "recording" ? " is-recording" : ""}`}
        aria-label={label}
        title={label}
        aria-pressed={state === "recording"}
        disabled={disabled || state === "starting" || state === "processing"}
        onClick={() => void toggle()}
      >
        <span aria-hidden="true">
          {state === "processing" ? "…" : state === "recording" ? "■" : (
            <svg viewBox="0 0 24 24">
              <rect x="8" y="3" width="8" height="12" rx="4" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
            </svg>
          )}
        </span>
      </button>
      {error && <span className="voice-input-error" role="alert">{error}</span>}
    </span>
  );
}
