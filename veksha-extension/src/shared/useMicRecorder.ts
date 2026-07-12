import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken } from "./api";
import { audioUploadMeta, pickAudioMime } from "./audio";
import { CONFIG } from "./config";
import { useT } from "./i18n";
import { isExtension } from "./platform";

export type MicState = "idle" | "recording" | "transcribing" | "error";

/**
 * Microphone recording + speech-to-text.
 *
 * Recording deliberately stays in the visible page that received the click.
 * Brave's temporary permission and Firefox/Zen's microphone grant are scoped
 * to that document and are not inherited reliably by an offscreen document or
 * a hidden background page.
 */
export function useMicRecorder(
  onResult: (text: string) => void,
  lang?: string,
  resumeTarget?: string,
): {
  state: MicState;
  volume: number;
  errorMsg: string;
  disabled: boolean;
  toggle: () => void;
} {
  const t = useT();
  const [state, setState] = useState<MicState>("idle");
  const [volume, setVolume] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");
  const [accountVoiceEnabled, setAccountVoiceEnabled] = useState(true);

  const stateRef = useRef<MicState>("idle");
  const onResultRef = useRef(onResult);
  const tRef = useRef(t);
  const langRef = useRef(lang);

  // The visible popup/page owns the recording state.
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const volumeTimerRef = useRef<number>(0);
  const localStopPendingRef = useRef(false);
  const recordingStartedAtRef = useRef(0);
  const speechDetectedRef = useRef(false);
  const lastSpeechAtRef = useRef(0);

  onResultRef.current = onResult;
  tRef.current = t;
  langRef.current = lang;

  function setS(nextState: MicState) {
    stateRef.current = nextState;
    setState(nextState);
  }

  function finishWithError(code?: string, detail?: string) {
    const strings = tRef.current;
    setVolume(0);
    setS("error");
    const friendly =
      code === "permission-denied"
        ? strings.mic_err_denied
        : code === "stt-failed"
        ? strings.mic_err_service
        : strings.mic_err_generic;
    setErrorMsg(detail ? `${friendly} (${detail})` : friendly);
  }

  function deliverText(text: string) {
    setVolume(0);
    if (!text) {
      setS("error");
      setErrorMsg(tRef.current.mic_err_none);
      return;
    }
    setS("idle");
    setErrorMsg("");
    onResultRef.current(text);
  }

  // ------------------------------------------------------------------
  // Extension-only account preference
  // ------------------------------------------------------------------

  useEffect(() => {
    if (!isExtension) return;

    let accountVoiceKey = "";
    chrome.storage.local.get([CONFIG.STORAGE_KEY_USERNAME]).then((result) => {
      const username = result[CONFIG.STORAGE_KEY_USERNAME] as string | undefined;
      if (!username) return;
      accountVoiceKey = `vk_voice_enabled_${username}`;
      return chrome.storage.local.get([accountVoiceKey]).then((accountResult) => {
        setAccountVoiceEnabled(accountResult[accountVoiceKey] !== false);
      });
    }).catch(() => {});
    const storageHandler = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "local") return;
      if (accountVoiceKey && changes[accountVoiceKey]) {
        setAccountVoiceEnabled(changes[accountVoiceKey].newValue !== false);
      }
    };
    chrome.storage.onChanged.addListener(storageHandler);

    return () => {
      chrome.storage.onChanged.removeListener(storageHandler);
    };
  }, []);

  // ------------------------------------------------------------------
  // Visible-page MediaRecorder + POST /api/stt
  // ------------------------------------------------------------------

  function localCleanup() {
    window.clearInterval(volumeTimerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }

  useEffect(() => {
    return () => localCleanup();
  }, []);

  async function localStart() {
    try {
      localStopPendingRef.current = false;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      recordingStartedAtRef.current = Date.now();
      speechDetectedRef.current = false;
      lastSpeechAtRef.current = recordingStartedAtRef.current;

      // Lightweight volume meter for the recording indicator.
      try {
        const ctx = new AudioContext();
        audioCtxRef.current = ctx;
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const buf = new Float32Array(analyser.fftSize);
        volumeTimerRef.current = window.setInterval(() => {
          analyser.getFloatTimeDomainData(buf);
          let sum = 0;
          for (let index = 0; index < buf.length; index++) sum += buf[index] * buf[index];
          const rms = Math.sqrt(sum / buf.length);
          setVolume(Math.min(1, rms * 8));

          const now = Date.now();
          if (rms >= 0.012) {
            speechDetectedRef.current = true;
            lastSpeechAtRef.current = now;
          }
          const silenceReached = speechDetectedRef.current && now - lastSpeechAtRef.current >= 1200;
          const maxDurationReached = now - recordingStartedAtRef.current >= 12000;
          const activeRecorder = recorderRef.current;
          if ((silenceReached || maxDurationReached) && activeRecorder?.state === "recording") {
            setS("transcribing");
            setVolume(0);
            activeRecorder.stop();
          }
        }, 50);
      } catch { /* volume meter is cosmetic */ }

      const chunks: Blob[] = [];
      const mimeType = pickAudioMime();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const meta = audioUploadMeta(recorder.mimeType);
      recorderRef.current = recorder;
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = async () => {
        localCleanup();
        try {
          const audio = new Blob(chunks, { type: meta.type });
          if (!audio.size) { deliverText(""); return; }
          const form = new FormData();
          form.append("file", audio, meta.filename);
          const language = langRef.current;
          if (language) form.append("language", language);
          const token = await getAuthToken();
          const res = await fetch(`${CONFIG.BACKEND_URL}/api/stt`, {
            method: "POST",
            body: form,
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          });
          if (!res.ok) throw new Error(`STT HTTP ${res.status}`);
          const json = (await res.json()) as { text?: string };
          deliverText((json.text ?? "").trim());
        } catch (err) {
          finishWithError("stt-failed", err instanceof Error ? err.message : String(err));
        }
      };
      recorder.start();
      // A second click can arrive while getUserMedia is still pending. Honour
      // that stop as soon as MediaRecorder is ready instead of recording in
      // the background while the UI is stuck on "transcribing".
      if (localStopPendingRef.current && recorder.state !== "inactive") recorder.stop();
    } catch (err) {
      localCleanup();
      const name = (err as DOMException)?.name;
      const permissionDenied = name === "NotAllowedError" || name === "SecurityError";
      if (permissionDenied && isExtension) {
        setS("idle");
        setErrorMsg("");
        try {
          const response = await chrome.runtime.sendMessage({
            type: "VOICE_PERMISSION_REQUEST",
            resumeTarget,
          }) as { ok?: boolean; error?: string } | undefined;
          if (response?.ok) return;
          finishWithError("permission-denied", response?.error || name);
          return;
        } catch (permissionError) {
          finishWithError("permission-denied", permissionError instanceof Error ? permissionError.message : name);
          return;
        }
      }
      finishWithError(
        permissionDenied ? "permission-denied" : "capture-failed",
        name || undefined,
      );
    }
  }

  const toggle = useCallback(() => {
    if (!accountVoiceEnabled) return;
    if (stateRef.current === "recording") {
      setS("transcribing");
      setVolume(0);
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      else localStopPendingRef.current = true;
      return;
    }

    if (stateRef.current !== "idle" && stateRef.current !== "error") return;

    setErrorMsg("");
    setVolume(0);
    setS("recording");

    void localStart();
  }, [accountVoiceEnabled, resumeTarget]);

  return { state, volume, errorMsg, disabled: !accountVoiceEnabled, toggle };
}
