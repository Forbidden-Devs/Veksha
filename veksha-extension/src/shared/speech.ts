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
  utterance.rate = 0.95;
  utterance.pitch = 1;

  const voices = synth.getVoices();
  utterance.voice =
    voices.find((voice) => voice.lang.toLowerCase() === locale.toLowerCase())
    ?? voices.find((voice) => voice.lang.toLowerCase().startsWith(`${prefix}-`))
    ?? null;

  synth.cancel();
  synth.speak(utterance);
  return true;
}
