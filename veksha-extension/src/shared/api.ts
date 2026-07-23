import { CONFIG } from "./config";
import { onStorageKeyChanged, runtimeSend, storageGet } from "./platform";
import type {
  KBSummaryData,
  LessonTopicSummary,
  MessageResponse,
  RemindersData,
  SettingsData,
  TranslateResponse,
  WordEntry,
} from "./types";

// ---------------------------------------------------------------------------
// Auth token
//
// The bearer token is issued once by POST /api/auth/register and stored in
// chrome.storage.local. Every context (popup, content script, background,
// offscreen) reads it lazily from storage and caches it in-module.
// The legacy `username` parameters on the functions below are kept so call
// sites stay unchanged — the server derives the user from the token.
// ---------------------------------------------------------------------------

let _token: string | null = null;

export function setAuthToken(token: string | null): void {
  _token = token;
}

export async function getAuthToken(): Promise<string> {
  if (_token) return _token;
  try {
    const st = await storageGet([CONFIG.STORAGE_KEY_TOKEN]);
    _token = (st[CONFIG.STORAGE_KEY_TOKEN] as string) || "";
  } catch {
    _token = "";
  }
  return _token;
}

// Keep the cache in sync if another extension context updates the token.
onStorageKeyChanged(CONFIG.STORAGE_KEY_TOKEN, (newValue) => {
  _token = (newValue as string) || null;
});

async function _authHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// HTTP helpers
//
// Content scripts never fetch() directly: in Firefox such requests run with
// the page's privileges and get blocked by the site's CSP (connect-src), and
// Chrome subjects them to the page's CORS. They are proxied through the
// background (VEKSHA_API_FETCH), which has extension privileges. Extension
// pages (popup/offscreen/background itself) and the web app fetch directly.
// ---------------------------------------------------------------------------

const IS_CONTENT_SCRIPT =
  typeof chrome !== "undefined" && !!chrome.runtime?.id &&
  typeof location !== "undefined" && /^https?:$/.test(location.protocol);

interface ProxiedFetchResult {
  ok: boolean;
  status: number;
  body: string;
  error?: string;
}

async function _request(
  path: string,
  init: { method: string; headers: Record<string, string>; body?: string },
  timeoutMs: number,
): Promise<{ ok: boolean; status: number; text: string }> {
  if (IS_CONTENT_SCRIPT) {
    const resp = (await chrome.runtime.sendMessage({
      type: "VEKSHA_API_FETCH",
      path,
      method: init.method,
      headers: init.headers,
      body: init.body,
      timeoutMs,
    })) as ProxiedFetchResult | undefined;
    if (!resp) throw new Error(`${path}: no response from background`);
    if (resp.error) throw new Error(`${path}: ${resp.error}`);
    return { ok: resp.ok, status: resp.status, text: resp.body };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${CONFIG.BACKEND_URL}${path}`, { ...init, signal: controller.signal });
    return { ok: res.ok, status: res.status, text: await res.text() };
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error(`${path} timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function _parse<T>(path: string, res: { ok: boolean; status: number; text: string }): T {
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}: ${res.text.slice(0, 300)}`);
  }
  return JSON.parse(res.text) as T;
}

function _withQuery(path: string, params?: Record<string, string>): string {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null) query.set(k, v);
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

async function _post<T>(
  path: string,
  body: Record<string, unknown>,
  timeoutMs = 30_000
): Promise<T> {
  const res = await _request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await _authHeaders()) },
    body: JSON.stringify(body),
  }, timeoutMs);
  return _parse<T>(path, res);
}

async function _delete<T>(path: string, params?: Record<string, string>): Promise<T> {
  const res = await _request(_withQuery(path, params), {
    method: "DELETE",
    headers: await _authHeaders(),
  }, 30_000);
  return _parse<T>(path, res);
}

async function _get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const res = await _request(_withQuery(path, params), {
    method: "GET",
    headers: await _authHeaders(),
  }, 30_000);
  return _parse<T>(path, res);
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface RegisterResponse {
  username: string; // internal account id, not the user-facing name
  token: string;
  display_name: string;
}

/** Register a new account with a display name; the server generates the
 *  internal account id. The caller must persist the returned token. */
export async function register(displayName: string): Promise<RegisterResponse> {
  const res = await fetch(`${CONFIG.BACKEND_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    throw new Error(`/api/auth/register -> HTTP ${res.status}: ${errBody.slice(0, 300)}`);
  }
  return res.json() as Promise<RegisterResponse>;
}

export interface GoogleAuthResponse extends RegisterResponse {
  created: boolean; // true when this login created a brand-new account
}

/** Sign in with a Google ID token; the caller must persist the returned token. */
export async function googleAuth(idToken: string): Promise<GoogleAuthResponse> {
  const res = await fetch(`${CONFIG.BACKEND_URL}/api/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    throw new Error(`/api/auth/google -> HTTP ${res.status}: ${errBody.slice(0, 300)}`);
  }
  return res.json() as Promise<GoogleAuthResponse>;
}

export interface AccountData {
  username: string; // internal account id
  display_name: string;
  google_linked: boolean;
  google_email: string;
}

export function getAccount(): Promise<AccountData> {
  return _get("/api/auth/account");
}

/** Attach a Google identity to the current account (409 if taken). */
export function googleLink(idToken: string): Promise<{ ok: boolean; email: string }> {
  return _post("/api/auth/google/link", { id_token: idToken });
}

// ---------------------------------------------------------------------------
// Billing (Telegram Stars subscriptions)
// ---------------------------------------------------------------------------

export interface BillingStatus {
  tier: "free" | "premium";
  expires_at: number | null; // unix seconds; null on the free tier
  features: string[];        // premium feature flags active for this user
  telegram_linked: boolean;
}

export function getBillingStatus(): Promise<BillingStatus> {
  return _get("/api/billing/status");
}

export interface BillingFeature {
  id: "grammar_lens" | "immersion" | "dual_subtitles";
  stars_monthly: number;
}

export function getBillingFeatures(): Promise<BillingFeature[]> {
  return _get("/api/billing/features");
}

/** Create a one-time deep link into the companion bot
 *  (t.me/<bot>?start=<code>) that binds this account to a Telegram user. */
export function createTelegramBillingLink(features: string[]): Promise<{ code: string; url: string }> {
  return _post("/api/billing/telegram/link", { features });
}

export function cancelSubscription(): Promise<BillingStatus> {
  return _delete("/api/billing/subscription");
}

export interface PromoRedeemResult {
  ok: boolean;
  tier: "free" | "premium";
  expires_at: number | null;
  error: "invalid" | "exhausted" | "already_redeemed" | null;
}

/** Redeem a manually-issued promo code for a temporary Premium grant.
 *  `ok: false` with `error` set means the code was rejected — not a
 *  network/HTTP failure, so callers don't need a try/catch for it. */
export function redeemPromoCode(code: string): Promise<PromoRedeemResult> {
  return _post("/api/billing/promo/redeem", { code });
}

// ---------------------------------------------------------------------------
// API calls (user derived from the bearer token server-side)
// ---------------------------------------------------------------------------

export function sendMessage(username: string, text: string): Promise<MessageResponse> {
  return _post("/api/message", { text });
}

export function translate(
  username: string,
  text: string,
  sourceLang: string,
  targetLang: string,
  bidirectional = false
): Promise<TranslateResponse> {
  return _post("/api/translate", {
    text,
    source_lang: sourceLang,
    target_lang: targetLang,
    bidirectional,
  });
}

export async function quickTranslate(
  username: string,
  text: string,
  sourceLang: string,
  targetLang: string,
  bidirectional = false,
): Promise<TranslateResponse> {
  const resp = await _post<TranslateResponse>(
    "/api/quick_translate",
    { text, source_lang: sourceLang, target_lang: targetLang, bidirectional },
    15_000
  );
  // Every translation quietly saves a word — tell the background so it can
  // schedule the "first review" nudge after the first few words.
  runtimeSend({ type: "VEKSHA_WORD_SAVED" });
  return resp;
}

export interface ImmersionSentence {
  text: string;
  cefr: string;
  translation: string;
}

export function analyzeImmersion(
  username: string,
  blocks: string[]
): Promise<{ blocks: { sentences: ImmersionSentence[] }[] }> {
  return _post("/api/immersion/analyze", { blocks }, 45_000);
}

export interface CiMeterResult {
  known_pct: number;
  cefr: string;
  user_level: string;
  verdict: "ideal" | "too_easy" | "too_hard" | "close";
  source: "local" | "llm";
  confidence: "low" | "high";
}

export function analyzeCiMeter(text: string, refine = false): Promise<CiMeterResult> {
  return _post("/api/ci_meter/analyze", { text, refine }, 20_000);
}

export type GrammarRole = "subject" | "verb" | "object" | "place" | "time" | "modifier";

export interface GrammarSegment {
  text: string;
  role: GrammarRole;
  explanation: string;
}

export type GrammarCategory =
  | "tense_aspect" | "voice" | "mood_modality" | "clause_link"
  | "negation_question" | "agreement_form" | "determiner_article"
  | "verb_pattern" | "word_order" | "comparison";

export interface GrammarAnnotation {
  text: string;
  category: GrammarCategory;
  label: string;
  explanation: string;
}

export interface GrammarBlockAnalysis {
  segments: GrammarSegment[];
  annotations: GrammarAnnotation[];
}

export function analyzeGrammarLens(
  blocks: string[]
): Promise<{ blocks: GrammarBlockAnalysis[] }> {
  return _post("/api/grammar-lens/analyze", { blocks }, 45_000);
}

export interface VocabFrequencyEntry {
  word: string;
  count: number;
  domains: Record<string, number>;
  known: boolean;
}

export function trackVocabFrequency(text: string, domain: string): Promise<{ tracked: number }> {
  return _post("/api/vocab_frequency/track", { text, domain }, 15_000);
}

export function getVocabFrequencyTop(limit = 100): Promise<{ words: VocabFrequencyEntry[] }> {
  return _get("/api/vocab_frequency/top", { limit: String(limit) });
}

export interface SubtitleAlignmentGroup {
  src: number[];
  dst: number[];
}

export interface SubtitleTranslation {
  translation_tokens: string[];
  alignment: SubtitleAlignmentGroup[];
  detected_source_lang: string | null;
}

/** Translate one subtitle line (tokens as rendered) with word alignment. */
export function subtitleTranslate(
  tokens: string[],
  sourceLang: string,
  targetLang: string
): Promise<SubtitleTranslation> {
  return _post("/api/subtitles/translate", {
    tokens,
    source_lang: sourceLang,
    target_lang: targetLang,
  }, 20_000);
}

/** Translate adjacent subtitle cues together so the model gets context and playback is prefetched. */
export function subtitleTranslateBatch(
  lines: string[][],
  sourceLang: string,
  targetLang: string
): Promise<{ lines: SubtitleTranslation[] }> {
  return _post("/api/subtitles/translate-batch", {
    lines,
    source_lang: sourceLang,
    target_lang: targetLang,
  }, 45_000);
}

export function explain(username: string, text: string, translation: string): Promise<{ explanation: string }> {
  return _post("/api/explain", { text, translation });
}

export function getReminders(username: string): Promise<RemindersData> {
  return _get("/api/reminders");
}

export function getSettings(username: string): Promise<SettingsData> {
  return _get("/api/settings");
}

export function saveSettings(
  username: string,
  opts: {
    displayName?: string;
    englishLevel?: string | null;
    goals?: string;
    generalPrompt?: string;
    nativeLang: string;
    targetLang: string;
    targetLangs?: string[];
    languageSettings?: Record<string, { level: string; goals: string; prompt: string }>;
    reminderLevel?: number;
    overseer?: boolean;
    miningSameLevelExamples?: number;
    miningHigherLevelExamples?: number;
  }
): Promise<SettingsData> {
  const body: Record<string, unknown> = {
    native_lang: opts.nativeLang,
    target_lang: opts.targetLang,
    target_langs: opts.targetLangs ?? [opts.targetLang],
    language_settings: opts.languageSettings,
    goals: opts.goals ?? "",
    general_prompt: opts.generalPrompt ?? "",
    reminder_level: opts.reminderLevel ?? 2,
    overseer: opts.overseer ?? false,
  };
  if (opts.englishLevel) body.english_level = opts.englishLevel;
  if (opts.displayName?.trim()) body.display_name = opts.displayName.trim();
  if (opts.miningSameLevelExamples !== undefined) {
    body.mining_same_level_examples = opts.miningSameLevelExamples;
  }
  if (opts.miningHigherLevelExamples !== undefined) {
    body.mining_higher_level_examples = opts.miningHigherLevelExamples;
  }
  return _post("/api/settings", body);
}

export function debugReset(username: string): Promise<{ ok: boolean; deleted: string[] }> {
  return _post("/api/debug/reset", {});
}

export function debugSimulateTraining(
  username: string
): Promise<{ ok: boolean; words_updated: number; topic_updated: string | null }> {
  return _post("/api/debug/simulate-training", {});
}

export function debugAdvanceDay(
  username: string
): Promise<{ ok: boolean; words_shifted: number; reminder: RemindersData }> {
  return _post("/api/debug/advance-day", {});
}

export function getKbSummary(username: string): Promise<KBSummaryData> {
  return _get("/api/kb_summary");
}

export function getKbWords(username: string): Promise<{ words: WordEntry[] }> {
  return _get("/api/kb_words");
}

export function getKbWordDetails(username: string, word: string): Promise<WordEntry> {
  return _get(`/api/kb_word_details?word=${encodeURIComponent(word)}`);
}

export function mineKbWord(username: string, word: string, force = false): Promise<WordEntry> {
  return _post("/api/kb_word_mine", { word, force }, 45_000);
}

export function reviewKbWord(username: string, word: string, rating: "again" | "good"): Promise<{ ok: boolean; next_review: number }> {
  return _post("/api/kb_word_review", { word, rating });
}

export function deleteKbWord(username: string, word: string): Promise<{ ok: boolean }> {
  return _delete("/api/kb_word", { word });
}

export function trainingInit(username: string): Promise<{ available_words: number }> {
  return _get("/api/training/init");
}

export function trainingValidate(username: string, wordNames: string[]): Promise<{ valid: string[] }> {
  return _post("/api/training/validate", { word_names: wordNames });
}

export function getLessonTopics(username: string): Promise<{ topics: LessonTopicSummary[] }> {
  return _get("/api/lesson-topics");
}

export function createLessonTopic(username: string, name: string): Promise<LessonTopicSummary> {
  return _post("/api/lesson-topics", { name });
}
