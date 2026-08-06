import { canRequestSpeech, synthesizeSpeech } from "./api";

const LANGUAGE_LOCALES: Record<string, string> = {
  en: "en-US", ru: "ru-RU", es: "es-ES", fr: "fr-FR", de: "de-DE",
  it: "it-IT", pt: "pt-PT", pl: "pl-PL", uk: "uk-UA", tr: "tr-TR",
  ar: "ar-SA", he: "he-IL", zh: "zh-CN", ja: "ja-JP", ko: "ko-KR",
  hi: "hi-IN", nl: "nl-NL", sv: "sv-SE", fi: "fi-FI", cs: "cs-CZ",
  el: "el-GR", ka: "ka-GE", vi: "vi-VN", th: "th-TH", id: "id-ID",
};

const canUseLocalSpeech = (): boolean => Boolean(
  typeof window !== "undefined" && window.speechSynthesis && globalThis.SpeechSynthesisUtterance,
);

export const canSpeak = (): boolean => canRequestSpeech() || canUseLocalSpeech();

let currentAudio: HTMLAudioElement | null = null;
let currentObjectUrl = "";
const operationIds = new Map<string, string>();

function operationId(text: string, languageCode: string): string {
  const key = `${languageCode}\u0000${text}`;
  const existing = operationIds.get(key);
  if (existing) return existing;
  const generated = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  operationIds.set(key, generated);
  if (operationIds.size > 256) operationIds.delete(operationIds.keys().next().value as string);
  return generated;
}

function stopAudio(): void {
  currentAudio?.pause();
  currentAudio = null;
  if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
  currentObjectUrl = "";
}

function voiceQuality(voice: SpeechSynthesisVoice, locale: string): number {
  const descriptor = voice.name.toLowerCase();
  const exactLocale = voice.lang.toLowerCase() === locale.toLowerCase();
  const natural = /google|microsoft|apple|samantha|daniel|anna|milena/.test(descriptor);
  const enhanced = /compact|enhanced|natural|premium/.test(descriptor);
  const novelty = /zarvox|whisper|bells|boing|bubbles|cellos|organ|trinoids/.test(descriptor);
  return Number(exactLocale) * 20
    + Number(voice.localService) * 8
    + Number(natural) * 6
    + Number(enhanced) * 3
    - Number(novelty) * 50;
}

function preferredVoice(synth: SpeechSynthesis, locale: string): SpeechSynthesisVoice | null {
  const language = locale.split("-", 1)[0].toLowerCase();
  return synth.getVoices()
    .filter(({ lang }) => lang.toLowerCase().startsWith(language))
    .reduce<SpeechSynthesisVoice | null>((best, candidate) => (
      !best || voiceQuality(candidate, locale) > voiceQuality(best, locale) ? candidate : best
    ), null);
}

function speakLocally(cleanText: string, languageCode: string): boolean {
  if (!canUseLocalSpeech()) return false;
  const locale = LANGUAGE_LOCALES[languageCode] ?? languageCode;
  const synth = window.speechSynthesis;
  const utterance = new SpeechSynthesisUtterance(cleanText);
  Object.assign(utterance, {
    lang: locale,
    rate: 0.86,
    pitch: 1,
    voice: preferredVoice(synth, locale),
  });

  synth.cancel();
  synth.speak(utterance);
  return true;
}

export async function speakText(text: string, languageCode: string): Promise<boolean> {
  const cleanText = text.trim();
  if (!cleanText || !canSpeak()) return false;

  if (canRequestSpeech()) {
    try {
      const audioBlob = await synthesizeSpeech(
        cleanText,
        languageCode,
        operationId(cleanText, languageCode),
      );
      stopAudio();
      window.speechSynthesis?.cancel();
      currentObjectUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(currentObjectUrl);
      currentAudio = audio;
      audio.addEventListener("ended", stopAudio, { once: true });
      audio.addEventListener("error", stopAudio, { once: true });
      await audio.play();
      return true;
    } catch {
      stopAudio();
      // Local speech keeps lessons usable while the platform is unavailable
      // or when a browser blocks delayed audio playback.
    }
  }
  return speakLocally(cleanText, languageCode);
}
