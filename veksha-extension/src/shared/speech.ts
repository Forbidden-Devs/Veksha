const LANGUAGE_LOCALES: Record<string, string> = {
  en: "en-US", ru: "ru-RU", es: "es-ES", fr: "fr-FR", de: "de-DE",
  it: "it-IT", pt: "pt-PT", pl: "pl-PL", uk: "uk-UA", tr: "tr-TR",
  ar: "ar-SA", he: "he-IL", zh: "zh-CN", ja: "ja-JP", ko: "ko-KR",
  hi: "hi-IN", nl: "nl-NL", sv: "sv-SE", fi: "fi-FI", cs: "cs-CZ",
  el: "el-GR", ka: "ka-GE", vi: "vi-VN", th: "th-TH", id: "id-ID",
};

export const canSpeak = (): boolean => Boolean(
  typeof window !== "undefined"
  && window.speechSynthesis
  && globalThis.SpeechSynthesisUtterance,
);

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

export function speakText(text: string, languageCode: string): boolean {
  const cleanText = text.trim();
  if (!cleanText || !canSpeak()) return false;

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
