import { canRequestSpeech, transcribeSpeech } from "./api";

const MAX_RECORDING_MS = 29_000;

export interface VoiceRecording {
  stop(): Promise<Blob>;
  cancel(): Promise<void>;
}

export function canUseVoiceInput(): boolean {
  return canRequestSpeech()
    && typeof navigator !== "undefined"
    && Boolean(navigator.mediaDevices?.getUserMedia)
    && typeof window !== "undefined"
    && Boolean(window.AudioContext);
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

function pcmWav(chunks: Float32Array[], sampleRate: number): Blob {
  const samples = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + samples * 2, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, samples * 2, true);

  let offset = 44;
  for (const chunk of chunks) {
    for (const sample of chunk) {
      const clipped = Math.max(-1, Math.min(1, sample));
      view.setInt16(offset, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export async function startVoiceRecording(onLimit: () => void): Promise<VoiceRecording> {
  if (!canUseVoiceInput()) throw new Error("voice_input_unavailable");
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];
  processor.onaudioprocess = ({ inputBuffer }) => {
    const mono = new Float32Array(inputBuffer.length);
    for (let channel = 0; channel < inputBuffer.numberOfChannels; channel += 1) {
      const data = inputBuffer.getChannelData(channel);
      for (let index = 0; index < data.length; index += 1) mono[index] += data[index] / inputBuffer.numberOfChannels;
    }
    chunks.push(mono);
  };
  source.connect(processor);
  processor.connect(context.destination);

  let finished = false;
  const timer = window.setTimeout(onLimit, MAX_RECORDING_MS);
  async function close(): Promise<void> {
    if (finished) return;
    finished = true;
    window.clearTimeout(timer);
    processor.disconnect();
    source.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    await context.close();
  }
  return {
    async stop() {
      await close();
      return pcmWav(chunks, context.sampleRate);
    },
    cancel: close,
  };
}

export async function transcribeRecording(audio: Blob, language?: string): Promise<string> {
  const operationId = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  const result = await transcribeSpeech(audio, operationId, language);
  return result.text.trim();
}
