/**
 * capture.ts — microphone recording + OCR, shared between browser targets.
 *
 * Chrome MV3 backgrounds are service workers with no DOM, so this runs inside
 * the offscreen document (src/offscreen) and talks to the background via
 * runtime messages. Firefox has no offscreen API, but its MV3 background is an
 * event page with full DOM access — there the background imports this module
 * and calls it directly. `emit` abstracts the reply channel for both cases.
 */
import { CONFIG } from "./config";
import { audioUploadMeta, pickAudioMime } from "./audio";
import { createWorker, type Worker as TessWorker } from "tesseract.js";

const FRAME_MS = 50;

// OCR languages bundled under public/tesseract/lang (Latin + Cyrillic starter).
const OCR_LANGS = "eng+rus+spa";

export type CaptureEmit = (message: Record<string, unknown>) => void;

export interface VoiceStartOptions {
  requestId: string;
  language?: string;
  token?: string;
}

export interface CaptureController {
  startVoice(opts: VoiceStartOptions): Promise<void>;
  stopVoice(): Promise<void>;
  handleOcrRegion(msg: Record<string, unknown>): Promise<void>;
}

interface OcrRect { x: number; y: number; w: number; h: number; }

const OCR_UPSCALE = 2;

function loadImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = reject;
    el.src = dataUrl;
  });
}

/** Average colour of the crop's border pixels — a cheap "background" estimate
 *  used to paint over the original text before laying the translation on top. */
function borderColor(ctx: CanvasRenderingContext2D, w: number, h: number): string {
  const d = ctx.getImageData(0, 0, w, h).data;
  let r = 0, g = 0, b = 0, n = 0;
  const at = (x: number, y: number) => { const i = (y * w + x) * 4; r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; };
  for (let x = 0; x < w; x += 2) { at(x, 0); at(x, h - 1); }
  for (let y = 0; y < h; y += 2) { at(0, y); at(w - 1, y); }
  if (!n) return "rgb(255,255,255)";
  return `rgb(${Math.round(r / n)}, ${Math.round(g / n)}, ${Math.round(b / n)})`;
}

interface OcrLine { text: string; bbox: { x: number; y: number; w: number; h: number }; }

function isPermissionError(err: unknown): boolean {
  return err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "SecurityError");
}

export function createCaptureController(emit: CaptureEmit): CaptureController {
  let ocrWorker: TessWorker | null = null;
  let ocrWorkerPromise: Promise<TessWorker> | null = null;

  function getOcrWorker(): Promise<TessWorker> {
    if (ocrWorker) return Promise.resolve(ocrWorker);
    if (!ocrWorkerPromise) {
      ocrWorkerPromise = createWorker(OCR_LANGS, 1, {
        workerPath: chrome.runtime.getURL("tesseract/worker.min.js"),
        corePath: chrome.runtime.getURL("tesseract/"),
        langPath: chrome.runtime.getURL("tesseract/lang"),
        workerBlobURL: false,
      }).then((w) => {
        ocrWorker = w;
        return w;
      });
    }
    return ocrWorkerPromise;
  }

  async function handleOcrRegion(msg: Record<string, unknown>): Promise<void> {
    const requestId = String(msg.requestId || "");
    const rect = msg.rect as OcrRect;
    const viewportW = Number(msg.viewportW) || 0;
    const viewportH = Number(msg.viewportH) || 0;
    try {
      const img = await loadImage(msg.dataUrl as string);
      const scaleX = img.naturalWidth / (viewportW || img.naturalWidth);
      const scaleY = img.naturalHeight / (viewportH || img.naturalHeight);
      const sx = Math.max(0, rect.x * scaleX);
      const sy = Math.max(0, rect.y * scaleY);
      const sw = Math.max(1, rect.w * scaleX);
      const sh = Math.max(1, rect.h * scaleY);
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(sw * OCR_UPSCALE);
      canvas.height = Math.round(sh * OCR_UPSCALE);
      const ctx = canvas.getContext("2d")!;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);

      const bg = borderColor(ctx, canvas.width, canvas.height);

      // Grayscale, downscaled snapshot of the region for later screenshot
      // matching (TD must match the content script's TRACK_D). Returning it here
      // saves a second captureVisibleTab call in the content script.
      const TD = 8; // must match the content script's TRACK_D
      const tc = document.createElement("canvas");
      tc.width = Math.max(1, Math.round(sw / TD));
      tc.height = Math.max(1, Math.round(sh / TD));
      const tctx = tc.getContext("2d")!;
      tctx.drawImage(img, sx, sy, sw, sh, 0, 0, tc.width, tc.height);
      const tpx = tctx.getImageData(0, 0, tc.width, tc.height).data;
      const tmplData = new Array<number>(tc.width * tc.height);
      for (let i = 0, p = 0; p < tmplData.length; p++, i += 4) tmplData[p] = (tpx[i] * 0.299 + tpx[i + 1] * 0.587 + tpx[i + 2] * 0.114) | 0;
      const tmpl = { w: tc.width, h: tc.height, data: tmplData };

      const worker = await getOcrWorker();
      // Ask for the structured layout (blocks/paragraphs/lines) — in tesseract.js
      // v6+ it isn't returned unless requested, which left us with a single line.
      const { data } = await worker.recognize(canvas, {}, { blocks: true } as unknown as undefined);
      const text = (data.text || "").replace(/\s+\n/g, "\n").trim();

      // Collect per-line boxes, preferring data.lines but falling back to walking
      // blocks → paragraphs → lines (whichever this version populates).
      type RawLine = { text: string; bbox: { x0: number; y0: number; x1: number; y1: number } };
      const d = data as unknown as {
        lines?: RawLine[];
        blocks?: Array<{ paragraphs?: Array<{ lines?: RawLine[] }> }>;
      };
      let raw: RawLine[] = Array.isArray(d.lines) && d.lines.length ? d.lines : [];
      if (!raw.length && Array.isArray(d.blocks)) {
        for (const b of d.blocks) for (const p of b.paragraphs ?? []) for (const l of p.lines ?? []) raw.push(l);
      }

      // Map line boxes (canvas px) back to region-local CSS px.
      const fx = scaleX * OCR_UPSCALE, fy = scaleY * OCR_UPSCALE;
      let lines: OcrLine[] = raw
        .map((l) => ({
          text: (l.text || "").replace(/\s+/g, " ").trim(),
          bbox: {
            x: l.bbox.x0 / fx,
            y: l.bbox.y0 / fy,
            w: (l.bbox.x1 - l.bbox.x0) / fx,
            h: (l.bbox.y1 - l.bbox.y0) / fy,
          },
        }))
        .filter((l) => l.text);
      if (!lines.length && text) lines = [{ text, bbox: { x: 0, y: 0, w: rect.w, h: rect.h } }];

      emit({ type: "OCR_RESULT", requestId, text, lines, bg, tmpl });
    } catch (err) {
      console.error("[ocr/capture] failed:", err);
      emit({ type: "OCR_ERROR", requestId, error: String(err) });
    }
  }

  let requestId: string | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let audioCtx: AudioContext | null = null;
  let stream: MediaStream | null = null;
  let frameTimer: ReturnType<typeof setInterval> | null = null;
  let chunks: Blob[] = [];
  let isRecording = false;
  let currentLanguage = "";
  let currentToken = "";
  let voiceStartedAt = 0;
  let speechDetected = false;
  let lastSpeechAt = 0;
  let voiceGeneration = 0;

  async function startVoice(opts: VoiceStartOptions) {
    if (isRecording) await stopVoice();
    const generation = ++voiceGeneration;
    requestId = opts.requestId;
    currentLanguage = opts.language ?? "";
    currentToken = opts.token ?? "";

    try {
      const acquiredStream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
      });
      // stopVoice may have been called while the permission/device request was
      // pending. Never let that stale request start an orphaned recording.
      if (generation !== voiceGeneration || requestId !== opts.requestId) {
        acquiredStream.getTracks().forEach(track => track.stop());
        return;
      }
      stream = acquiredStream;

      audioCtx = new AudioContext();
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      audioCtx.createMediaStreamSource(stream).connect(analyser);

      const mimeType = pickAudioMime();
      mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      chunks = [];
      mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      mediaRecorder.onerror = event => {
        console.error("[voice/capture] recorder error:", event);
        void stopVoice("recorder-error");
      };
      // A single final dataavailable event produces a self-contained WebM/Ogg
      // file. The volume meter does not need MediaRecorder timeslices.
      mediaRecorder.start();
      isRecording = true;
      voiceStartedAt = Date.now();
      speechDetected = false;
      lastSpeechAt = voiceStartedAt;

      const data = new Float32Array(analyser.fftSize);
      frameTimer = setInterval(() => {
        if (!isRecording || !requestId) return;
        analyser.getFloatTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        emit({ type: "VOICE_CAPTURE_VOLUME", requestId, volume: Math.min(1, rms * 8) });
        const now = Date.now();
        if (rms >= 0.012) {
          speechDetected = true;
          lastSpeechAt = now;
        }
        if ((speechDetected && now - lastSpeechAt >= 1200) || now - voiceStartedAt >= 12000) {
          void stopVoice();
        }
      }, FRAME_MS);
    } catch (err) {
      if (generation !== voiceGeneration) return;
      console.error("[voice/capture] getUserMedia error:", err);
      cleanup();
      emit({
        type: "VOICE_CAPTURE_ERROR",
        requestId: opts.requestId,
        code: isPermissionError(err) ? "permission-denied" : "capture-failed",
        error: err instanceof Error ? err.name : String(err),
      });
    }
  }

  async function stopVoice(errorCode?: string) {
    ++voiceGeneration;
    if (!isRecording) {
      cleanup();
      return;
    }
    isRecording = false;
    if (frameTimer) {
      clearInterval(frameTimer);
      frameTimer = null;
    }

    const currentRequestId = requestId;
    const language = currentLanguage;
    const token = currentToken;
    const recorder = mediaRecorder;
    if (!currentRequestId || !recorder || recorder.state === "inactive") {
      cleanup();
      if (currentRequestId) emit({ type: "VOICE_CAPTURE_DONE", requestId: currentRequestId, text: "" });
      return;
    }

    if (errorCode) {
      cleanup();
      emit({ type: "VOICE_CAPTURE_ERROR", requestId: currentRequestId, code: errorCode });
      return;
    }

    const recordedMime = recorder.mimeType;
    const finalChunks = await new Promise<Blob[]>(resolve => {
      const extra: Blob[] = [];
      recorder.ondataavailable = event => {
        if (event.data.size > 0) extra.push(event.data);
      };
      recorder.onstop = () => resolve([...chunks, ...extra]);
      recorder.stop();
    });

    cleanup();

    try {
      const meta = audioUploadMeta(recordedMime);
      const audio = new Blob(finalChunks, { type: meta.type });
      if (!audio.size) {
        emit({ type: "VOICE_CAPTURE_DONE", requestId: currentRequestId, text: "" });
        return;
      }

      const form = new FormData();
      form.append("file", audio, meta.filename);
      if (language) form.append("language", language);
      const res = await fetch(`${CONFIG.BACKEND_URL}/api/stt`, {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`STT HTTP ${res.status}: ${body.slice(0, 240)}`);
      }
      const json = await res.json() as { text?: string };
      emit({ type: "VOICE_CAPTURE_DONE", requestId: currentRequestId, text: json.text?.trim() ?? "" });
    } catch (err) {
      console.error("[voice/capture] STT error:", err);
      emit({ type: "VOICE_CAPTURE_ERROR", requestId: currentRequestId, code: "stt-failed", error: String(err) });
    }
  }

  function cleanup() {
    stream?.getTracks().forEach(track => track.stop());
    audioCtx?.close().catch(() => {});
    if (frameTimer) clearInterval(frameTimer);
    stream = null;
    audioCtx = null;
    mediaRecorder = null;
    frameTimer = null;
    chunks = [];
    isRecording = false;
    requestId = null;
    currentLanguage = "";
    currentToken = "";
  }

  return { startVoice, stopVoice, handleOcrRegion };
}
