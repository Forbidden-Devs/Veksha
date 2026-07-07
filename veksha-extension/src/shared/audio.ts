/**
 * audio.ts — MediaRecorder format negotiation.
 *
 * Chrome records audio/webm;codecs=opus; Firefox may only offer ogg/opus.
 * The backend forwards filename + content type to the STT service, so both
 * containers are accepted — we just have to ask for one the browser supports.
 */

const CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

/** Best supported recording mime type, or undefined to let the browser pick. */
export function pickAudioMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t));
}

/** Container mime (no codec params) and filename for an STT upload. */
export function audioUploadMeta(recorderMime: string | undefined): { type: string; filename: string } {
  const base = (recorderMime || "audio/webm").split(";")[0].trim().toLowerCase();
  const ext = base === "audio/ogg" ? "ogg" : base === "audio/mp4" ? "mp4" : "webm";
  const type = ext === "webm" ? "audio/webm" : base;
  return { type, filename: `speech.${ext}` };
}
