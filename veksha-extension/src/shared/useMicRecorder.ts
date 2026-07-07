import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken } from "./api";
import { audioUploadMeta, pickAudioMime } from "./audio";
import { CONFIG } from "./config";
import { useT } from "./i18n";
import { isExtension } from "./platform";

export type MicState = "idle" | "recording" | "transcribing" | "error";

type VoiceMessage = {
  type?: string;
  requestId?: string;
  volume?: number;
  text?: string;
  code?: string;
};

function createRequestId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Microphone recording + speech-to-text.
 *
 * In the extension the popup can close at any moment, so recording is
 * delegated to the offscreen document via runtime messages. On the web the
 * page owns its lifetime — record locally with MediaRecorder and POST the
 * clip to /api/stt directly.
 */
export function useMicRecorder(
  onResult: (text: string) => void,
  lang?: string,
): {
  state: MicState;
  volume: number;
  errorMsg: string;
  toggle: () => void;
} {
  const t = useT();
  const [state, setState] = useState<MicState>("idle");
  const [volume, setVolume] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");

  const stateRef = useRef<MicState>("idle");
  const requestIdRef = useRef<string | null>(null);
  const onResultRef = useRef(onResult);
  const tRef = useRef(t);
  const langRef = useRef(lang);

  // Web recording state
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const volumeTimerRef = useRef<number>(0);

  onResultRef.current = onResult;
  tRef.current = t;
  langRef.current = lang;

  function setS(nextState: MicState) {
    stateRef.current = nextState;
    setState(nextState);
  }

  function finishWithError(code?: string) {
    const strings = tRef.current;
    requestIdRef.current = null;
    setVolume(0);
    setS("error");
    setErrorMsg(
      code === "permission-denied"
        ? strings.mic_err_denied
        : code === "stt-failed"
        ? strings.mic_err_service
        : strings.mic_err_generic,
    );
  }

  function deliverText(text: string) {
    requestIdRef.current = null;
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
  // Extension path: offscreen document via runtime messages
  // ------------------------------------------------------------------

  useEffect(() => {
    if (!isExtension) return;

    const handler = (msg: VoiceMessage) => {
      if (!msg.type?.startsWith("VOICE_CAPTURE_")) return;
      if (!requestIdRef.current || msg.requestId !== requestIdRef.current) return;

      if (msg.type === "VOICE_CAPTURE_VOLUME") {
        setVolume(typeof msg.volume === "number" ? msg.volume : 0);
        return;
      }
      if (msg.type === "VOICE_CAPTURE_DONE") {
        deliverText((msg.text ?? "").trim());
        return;
      }
      if (msg.type === "VOICE_CAPTURE_ERROR") {
        finishWithError(msg.code);
      }
    };

    chrome.runtime.onMessage.addListener(handler);
    return () => {
      chrome.runtime.onMessage.removeListener(handler);
      if (requestIdRef.current && stateRef.current === "recording") {
        chrome.runtime.sendMessage({ type: "VOICE_CAPTURE_STOP", requestId: requestIdRef.current }).catch(() => {});
      }
    };
  }, []);

  // ------------------------------------------------------------------
  // Web path: local MediaRecorder + POST /api/stt
  // ------------------------------------------------------------------

  function webCleanup() {
    window.clearInterval(volumeTimerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }

  useEffect(() => {
    if (isExtension) return;
    return () => webCleanup();
  }, []);

  async function webStart() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Lightweight volume meter for the recording indicator.
      try {
        const ctx = new AudioContext();
        audioCtxRef.current = ctx;
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const buf = new Uint8Array(analyser.frequencyBinCount);
        volumeTimerRef.current = window.setInterval(() => {
          analyser.getByteFrequencyData(buf);
          const avg = buf.reduce((a, b) => a + b, 0) / buf.length;
          setVolume(Math.min(1, avg / 128));
        }, 100);
      } catch { /* volume meter is cosmetic */ }

      const chunks: Blob[] = [];
      const mimeType = pickAudioMime();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const meta = audioUploadMeta(recorder.mimeType);
      recorderRef.current = recorder;
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = async () => {
        webCleanup();
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
        } catch {
          finishWithError("stt-failed");
        }
      };
      recorder.start();
    } catch (err) {
      webCleanup();
      const name = (err as DOMException)?.name;
      finishWithError(name === "NotAllowedError" ? "permission-denied" : "capture-failed");
    }
  }

  const toggle = useCallback(() => {
    if (stateRef.current === "recording") {
      setS("transcribing");
      setVolume(0);
      if (isExtension) {
        chrome.runtime.sendMessage({ type: "VOICE_CAPTURE_STOP", requestId: requestIdRef.current }).catch(() => {
          finishWithError("capture-failed");
        });
      } else {
        recorderRef.current?.stop();
      }
      return;
    }

    if (stateRef.current !== "idle" && stateRef.current !== "error") return;

    const requestId = createRequestId();
    requestIdRef.current = requestId;
    setErrorMsg("");
    setVolume(0);
    setS("recording");

    if (isExtension) {
      chrome.runtime.sendMessage({
        type: "VOICE_CAPTURE_START",
        requestId,
        language: langRef.current,
      }).catch((err) => {
        console.error("[voice] start failed:", err);
        finishWithError("capture-failed");
      });
    } else {
      void webStart();
    }
  }, []);

  return { state, volume, errorMsg, toggle };
}
