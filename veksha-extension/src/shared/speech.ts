const LANGUAGE_LOCALES: Record<string, string> = {
  en: "en-US", ru: "ru-RU", es: "es-ES", fr: "fr-FR", de: "de-DE",
  it: "it-IT", pt: "pt-PT", pl: "pl-PL", uk: "uk-UA", tr: "tr-TR",
  ar: "ar-SA", he: "he-IL", zh: "zh-CN", ja: "ja-JP", ko: "ko-KR",
  hi: "hi-IN", nl: "nl-NL", sv: "sv-SE", fi: "fi-FI", cs: "cs-CZ",
  el: "el-GR", ka: "ka-GE", vi: "vi-VN", th: "th-TH", id: "id-ID",
};

// Map a short language code (or pass-through BCP-47) to a locale for the
// browser's built-in SpeechRecognition. Falls back to the browser UI language.
export function getRecognitionLocale(languageCode?: string): string {
  if (languageCode) return LANGUAGE_LOCALES[languageCode] ?? languageCode;
  return (typeof navigator !== "undefined" && navigator.language) || "en-US";
}

export function canSpeak(): boolean {
  return typeof window !== "undefined"
    && "speechSynthesis" in window
    && typeof SpeechSynthesisUtterance !== "undefined";
}

export function speakText(text: string, languageCode: string): boolean {
  const cleanText = text.trim();
  if (!cleanText || !canSpeak()) return false;

  const locale = LANGUAGE_LOCALES[languageCode] ?? languageCode;
  const prefix = locale.split("-")[0].toLowerCase();
  const synth = window.speechSynthesis;
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.lang = locale;
  utterance.rate = 0.86;
  utterance.pitch = 1;

  const voices = synth.getVoices();
  const matching = voices.filter((voice) => voice.lang.toLowerCase().startsWith(prefix));
  const score = (voice: SpeechSynthesisVoice) => {
    const name = voice.name.toLowerCase();
    let value = 0;
    if (voice.lang.toLowerCase() === locale.toLowerCase()) value += 20;
    if (voice.localService) value += 8;
    if (/google|microsoft|apple|samantha|daniel|anna|milena/.test(name)) value += 6;
    if (/compact|enhanced|natural|premium/.test(name)) value += 3;
    if (/zarvox|whisper|bells|boing|bubbles|cellos|organ|trinoids/.test(name)) value -= 50;
    return value;
  };
  utterance.voice = matching.sort((a, b) => score(b) - score(a))[0] ?? null;

  synth.cancel();
  synth.speak(utterance);
  return true;
}
