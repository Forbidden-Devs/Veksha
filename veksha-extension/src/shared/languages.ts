export interface Language {
  code: string;
  name: string;
}

// Keep the most commonly selected languages first. The remaining entries are
// every other ISO 639-1 language, so adding a language is no longer limited to
// the original starter set.
const FEATURED_LANGUAGES: Language[] = [
  { code: "en", name: "English" },
  { code: "ru", name: "Russian" },
  { code: "es", name: "Spanish" },
  { code: "fr", name: "French" },
  { code: "de", name: "German" },
  { code: "it", name: "Italian" },
  { code: "pt", name: "Portuguese" },
  { code: "pl", name: "Polish" },
  { code: "uk", name: "Ukrainian" },
  { code: "tr", name: "Turkish" },
  { code: "ar", name: "Arabic" },
  { code: "he", name: "Hebrew" },
  { code: "zh", name: "Chinese" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "hi", name: "Hindi" },
  { code: "nl", name: "Dutch" },
  { code: "sv", name: "Swedish" },
  { code: "fi", name: "Finnish" },
  { code: "cs", name: "Czech" },
  { code: "el", name: "Greek" },
  { code: "ka", name: "Georgian" },
  { code: "vi", name: "Vietnamese" },
  { code: "th", name: "Thai" },
  { code: "id", name: "Indonesian" },
];

const ISO_639_1_CODES = (
  "aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs " +
  "ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy " +
  "ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv " +
  "ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi " +
  "mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps " +
  "pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te " +
  "tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu"
).split(" ");

const featuredCodes = new Set(FEATURED_LANGUAGES.map(({ code }) => code));
const englishDisplayNames = new Intl.DisplayNames(["en"], { type: "language" });

export function getLanguageName(code: string): string {
  return FEATURED_LANGUAGES.find((language) => language.code === code)?.name
    ?? englishDisplayNames.of(code)
    ?? code.toUpperCase();
}

const OTHER_LANGUAGES = ISO_639_1_CODES
  .filter((code) => !featuredCodes.has(code))
  .map((code) => ({ code, name: getLanguageName(code) }))
  .sort((a, b) => a.name.localeCompare(b.name, "en"));

export const LANGUAGES: Language[] = [
  { code: "auto", name: "Detect language" },
  ...FEATURED_LANGUAGES,
  ...OTHER_LANGUAGES,
];

export const LANGUAGE_NAME_BY_CODE: Record<string, string> = Object.fromEntries(
  LANGUAGES.map((language) => [language.code, language.name])
);
