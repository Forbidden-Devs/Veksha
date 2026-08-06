export const CONFIG = {
  // Watch builds talk to the local FastAPI process. Production/store builds
  // keep the public HTTPS origin; __DEV_BUILD__ is injected by Vite.
  // The standalone web build can point previews/staging at another backend
  // through VITE_BACKEND_URL. Extension builds keep their fixed dev/prod pair.
  BACKEND_URL: import.meta.env.VITE_BACKEND_URL
    || (__DEV_BUILD__ ? "http://127.0.0.1:8000" : "https://api.veksha.app"),
  // Public Google OAuth client id ("Web application" type). Authentication
  // itself runs through the backend HTTPS callback; this value only enables
  // the UI and must match the backend's GOOGLE_CLIENT_ID.
  GOOGLE_CLIENT_ID: "213004589034-fgni2g4c9fmh10bn9quq9de5qn8h8kjc.apps.googleusercontent.com" as string,
  // Keep local credentials separate from production. The persistent browser
  // profile used by npm run dev may already contain a veksha.app bearer token,
  // which is invalid against a fresh local database.
  STORAGE_KEY_USERNAME: __DEV_BUILD__ ? "veksha_username_dev" : "veksha_username",
  STORAGE_KEY_TOKEN: __DEV_BUILD__ ? "veksha_token_dev" : "veksha_token",
  // One-shot handoff from the background OAuth task to a popup that may have
  // been destroyed while the Google tab had focus.
  STORAGE_KEY_GOOGLE_SIGNIN_RESULT: __DEV_BUILD__
    ? "veksha_google_signin_result_dev"
    : "veksha_google_signin_result",
  STORAGE_KEY_DUAL_SUBS_FEATURE: "veksha_dualsubs_feature_enabled",
  STORAGE_KEY_DUAL_SUBS_VISIBLE: "veksha_dualsubs_visible",
  STORAGE_KEY_SUBTITLE_STUDY: "veksha_subtitle_study_on",
  STORAGE_KEY_LANG_PAIR: "veksha_lang_pair",
  STORAGE_KEY_NATIVE_LANG: "veksha_native_lang",
  STORAGE_KEY_READING_COACH: "veksha_reading_coach_on",
  STORAGE_KEY_READING_SESSION: "veksha_reading_session",
  STORAGE_KEY_FOCUS_SESSION: "veksha_focus_session",
  STORAGE_KEY_AI_BLOCKLIST: "veksha_ai_blocklist",
  DEFAULT_SOURCE_LANG: "auto",
  DEFAULT_TARGET_LANG: "en",
  REMINDERS_ALARM_NAME: "veksha-reminders",
  REMINDERS_INTERVAL_MINUTES: 60,
  TRAINING_MAX_SESSION: 10,
  LESSON_QUESTIONS_PER_SESSION: 6,
} as const;
