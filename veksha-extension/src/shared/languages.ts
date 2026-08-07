export interface Language {
  code: string;
  name: string;
}

// Keep the most commonly selected languages first. The remaining entries are
// every other ISO 639-1 language, so adding a language is no longer limited to
// the original starter set.
const FEATURED_LANGUAGE_PAIRS = [
  ["en", "English"], ["ru", "Russian"], ["es", "Spanish"],
  ["fr", "French"], ["de", "German"], ["it", "Italian"],
  ["pt", "Portuguese"], ["pl", "Polish"], ["uk", "Ukrainian"],
  ["tr", "Turkish"], ["ar", "Arabic"], ["he", "Hebrew"],
  ["zh", "Chinese"], ["ja", "Japanese"], ["ko", "Korean"],
  ["hi", "Hindi"], ["nl", "Dutch"], ["sv", "Swedish"],
  ["fi", "Finnish"], ["cs", "Czech"], ["el", "Greek"],
  ["ka", "Georgian"], ["vi", "Vietnamese"], ["th", "Thai"],
  ["id", "Indonesian"],
] as const;

const FEATURED_LANGUAGES: Language[] = FEATURED_LANGUAGE_PAIRS.map(
  ([code, name]) => ({ code, name }),
);

// Explicit English names are stable fallbacks for browsers with reduced ICU.
const LANGUAGE_NAMES: Record<string, string> = {
  aa: "Afar",
  ab: "Abkhazian",
  ae: "Avestan",
  af: "Afrikaans",
  ak: "Akan",
  am: "Amharic",
  an: "Aragonese",
  ar: "Arabic",
  as: "Assamese",
  av: "Avaric",
  ay: "Aymara",
  az: "Azerbaijani",
  ba: "Bashkir",
  be: "Belarusian",
  bg: "Bulgarian",
  bh: "Bihari languages",
  bi: "Bislama",
  bm: "Bambara",
  bn: "Bengali",
  bo: "Tibetan",
  br: "Breton",
  bs: "Bosnian",
  ca: "Catalan",
  ce: "Chechen",
  ch: "Chamorro",
  co: "Corsican",
  cr: "Cree",
  cs: "Czech",
  cu: "Church Slavonic",
  cv: "Chuvash",
  cy: "Welsh",
  da: "Danish",
  de: "German",
  dv: "Divehi",
  dz: "Dzongkha",
  ee: "Ewe",
  el: "Greek",
  en: "English",
  eo: "Esperanto",
  es: "Spanish",
  et: "Estonian",
  eu: "Basque",
  fa: "Persian",
  ff: "Fulah",
  fi: "Finnish",
  fj: "Fijian",
  fo: "Faroese",
  fr: "French",
  fy: "Western Frisian",
  ga: "Irish",
  gd: "Scottish Gaelic",
  gl: "Galician",
  gn: "Guarani",
  gu: "Gujarati",
  gv: "Manx",
  ha: "Hausa",
  he: "Hebrew",
  hi: "Hindi",
  ho: "Hiri Motu",
  hr: "Croatian",
  ht: "Haitian Creole",
  hu: "Hungarian",
  hy: "Armenian",
  hz: "Herero",
  ia: "Interlingua",
  id: "Indonesian",
  ie: "Interlingue",
  ig: "Igbo",
  ii: "Sichuan Yi",
  ik: "Inupiaq",
  io: "Ido",
  is: "Icelandic",
  it: "Italian",
  iu: "Inuktitut",
  ja: "Japanese",
  jv: "Javanese",
  ka: "Georgian",
  kg: "Kongo",
  ki: "Kikuyu",
  kj: "Kuanyama",
  kk: "Kazakh",
  kl: "Greenlandic",
  km: "Khmer",
  kn: "Kannada",
  ko: "Korean",
  kr: "Kanuri",
  ks: "Kashmiri",
  ku: "Kurdish",
  kv: "Komi",
  kw: "Cornish",
  ky: "Kyrgyz",
  la: "Latin",
  lb: "Luxembourgish",
  lg: "Ganda",
  li: "Limburgish",
  ln: "Lingala",
  lo: "Lao",
  lt: "Lithuanian",
  lu: "Luba-Katanga",
  lv: "Latvian",
  mg: "Malagasy",
  mh: "Marshallese",
  mi: "Māori",
  mk: "Macedonian",
  ml: "Malayalam",
  mn: "Mongolian",
  mr: "Marathi",
  ms: "Malay",
  mt: "Maltese",
  my: "Burmese",
  na: "Nauruan",
  nb: "Norwegian Bokmål",
  nd: "North Ndebele",
  ne: "Nepali",
  ng: "Ndonga",
  nl: "Dutch",
  nn: "Norwegian Nynorsk",
  no: "Norwegian",
  nr: "South Ndebele",
  nv: "Navajo",
  ny: "Chichewa",
  oc: "Occitan",
  oj: "Ojibwe",
  om: "Oromo",
  or: "Odia",
  os: "Ossetian",
  pa: "Punjabi",
  pi: "Pali",
  pl: "Polish",
  ps: "Pashto",
  pt: "Portuguese",
  qu: "Quechua",
  rm: "Romansh",
  rn: "Kirundi",
  ro: "Romanian",
  ru: "Russian",
  rw: "Kinyarwanda",
  sa: "Sanskrit",
  sc: "Sardinian",
  sd: "Sindhi",
  se: "Northern Sami",
  sg: "Sango",
  si: "Sinhala",
  sk: "Slovak",
  sl: "Slovenian",
  sm: "Samoan",
  sn: "Shona",
  so: "Somali",
  sq: "Albanian",
  sr: "Serbian",
  ss: "Swati",
  st: "Southern Sotho",
  su: "Sundanese",
  sv: "Swedish",
  sw: "Swahili",
  ta: "Tamil",
  te: "Telugu",
  tg: "Tajik",
  th: "Thai",
  ti: "Tigrinya",
  tk: "Turkmen",
  tl: "Tagalog",
  tn: "Tswana",
  to: "Tongan",
  tr: "Turkish",
  ts: "Tsonga",
  tt: "Tatar",
  tw: "Twi",
  ty: "Tahitian",
  ug: "Uyghur",
  uk: "Ukrainian",
  ur: "Urdu",
  uz: "Uzbek",
  ve: "Venda",
  vi: "Vietnamese",
  vo: "Volapük",
  wa: "Walloon",
  wo: "Wolof",
  xh: "Xhosa",
  yi: "Yiddish",
  yo: "Yoruba",
  za: "Zhuang",
  zh: "Chinese",
  zu: "Zulu",
};

const ISO_639_1_CODES = Object.keys(LANGUAGE_NAMES);

const featuredCodes = new Set(FEATURED_LANGUAGES.map(({ code }) => code));

export function getLanguageName(code: string, locale = "en"): string {
  const fallback = FEATURED_LANGUAGES.find((language) => language.code === code)?.name
    ?? LANGUAGE_NAMES[code]
    ?? code.toUpperCase();
  if (code === "auto" || locale.toLowerCase().startsWith("en")) return fallback;
  try {
    const localized = new Intl.DisplayNames([locale], { type: "language" }).of(code);
    return localized && localized.toLowerCase() !== code.toLowerCase() ? localized : fallback;
  } catch {
    return fallback;
  }
}

export function getScriptName(code: string, locale = "en", fallback = code): string {
  const normalized = code.trim();
  if (!normalized) return fallback;
  try {
    const script = normalized[0].toUpperCase() + normalized.slice(1).toLowerCase();
    return new Intl.DisplayNames([locale], { type: "script" }).of(script) ?? fallback;
  } catch {
    return fallback;
  }
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
