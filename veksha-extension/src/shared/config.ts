export const CONFIG = {
  BACKEND_URL: "https://veksha-backend-production.up.railway.app",
  // Public Google OAuth client id ("Web application" type). Authentication
  // itself runs through the backend HTTPS callback; this value only enables
  // the UI and must match the backend's GOOGLE_CLIENT_ID.
  GOOGLE_CLIENT_ID: "213004589034-fgni2g4c9fmh10bn9quq9de5qn8h8kjc.apps.googleusercontent.com" as string,
  STORAGE_KEY_USERNAME: "veksha_username",
  STORAGE_KEY_TOKEN: "veksha_token",
  STORAGE_KEY_DUAL_SUBS_FEATURE: "veksha_dualsubs_feature_enabled",
  STORAGE_KEY_DUAL_SUBS: "veksha_dualsubs_on",
  STORAGE_KEY_LANG_PAIR: "veksha_lang_pair",
  STORAGE_KEY_NATIVE_LANG: "veksha_native_lang",
  STORAGE_KEY_IMMERSION: "veksha_immersion_on",
  STORAGE_KEY_CI_METER: "veksha_ci_meter_on",
  STORAGE_KEY_GRAMMAR_LENS: "veksha_grammar_lens_on",
  STORAGE_KEY_VOCAB_FREQ: "veksha_vocab_freq_on",
  DEFAULT_SOURCE_LANG: "auto",
  DEFAULT_TARGET_LANG: "en",
  REMINDERS_ALARM_NAME: "veksha-reminders",
  REMINDERS_INTERVAL_MINUTES: 60,
  TRAINING_MAX_SESSION: 10,
  LESSON_QUESTIONS_PER_SESSION: 6,
} as const;
