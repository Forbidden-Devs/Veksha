export const CONFIG = {
  BACKEND_URL: "http://127.0.0.1:8000",
  STORAGE_KEY_USERNAME: "veksha_username",
  STORAGE_KEY_TOKEN: "veksha_token",
  STORAGE_KEY_LANG_PAIR: "veksha_lang_pair",
  STORAGE_KEY_NATIVE_LANG: "veksha_native_lang",
  STORAGE_KEY_IMMERSION: "veksha_immersion_on",
  DEFAULT_SOURCE_LANG: "auto",
  DEFAULT_TARGET_LANG: "en",
  REMINDERS_ALARM_NAME: "veksha-reminders",
  REMINDERS_INTERVAL_MINUTES: 60,
  TRAINING_MAX_SESSION: 10,
  LESSON_QUESTIONS_PER_SESSION: 6,
} as const;