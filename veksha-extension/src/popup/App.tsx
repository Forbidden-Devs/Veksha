import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import * as api from "../shared/api";
import { CONFIG } from "../shared/config";
import { googleSignIn } from "../shared/googleAuth";
import { useI18n } from "../shared/i18n";
import { isExtension, sessionGet, sessionSet, storageGet, storageRemove, storageSet } from "../shared/platform";
import type { Screen, SettingsMode } from "../shared/types";
import { LessonWindow } from "./overlays/LessonWindow";
import { ReminderCard } from "./overlays/ReminderCard";
import { TrainingWindow } from "./overlays/TrainingWindow";
import { TranslatorScreen } from "./screens/TranslatorScreen";
import { HomeScreen } from "./screens/HomeScreen";
import { ImmersionScreen } from "./screens/ImmersionScreen";
import { DebugScreen } from "./screens/DebugScreen";
import { DictionaryScreen } from "./screens/DictionaryScreen";
import { LevelSetupScreen } from "./screens/LevelSetupScreen";
import { MyWordsScreen } from "./screens/MyWordsScreen";
import { NativeLangScreen } from "./screens/NativeLangScreen";
import { OnboardingScreen } from "./screens/OnboardingScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { StatisticsScreen } from "./screens/StatisticsScreen";
import { SubscriptionScreen, type SubscriptionIntent } from "./screens/SubscriptionScreen";
import { TargetLangScreen } from "./screens/TargetLangScreen";
import { LearningGoalsScreen } from "./screens/LearningGoalsScreen";
import { QuizletScreen } from "./screens/QuizletScreen";

// ---------------------------------------------------------------------------
// Content-script relay — sends a message, reinjecting the script if stale
// ---------------------------------------------------------------------------

async function sendToActiveTab(message: Record<string, unknown>): Promise<"ok" | "restricted" | "error"> {
  if (!isExtension) return "error";
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id) return "error";

  const tabId = tab.id;
  const url = tab.url ?? "";
  if (!url || url.startsWith("chrome://") || url.startsWith("chrome-extension://") || url.startsWith("moz-extension://") || url.startsWith("about:")) {
    return "restricted";
  }

  try {
    await chrome.tabs.sendMessage(tabId, message);
    return "ok";
  } catch {
    // Content script missing or stale — reinject and retry
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["src/content/content.js"] });
      await chrome.scripting.insertCSS({ target: { tabId }, files: ["src/content/content.css"] });
      await new Promise<void>((r) => setTimeout(r, 150));
      await chrome.tabs.sendMessage(tabId, message);
      return "ok";
    } catch {
      return "error";
    }
  }
}

// ---------------------------------------------------------------------------
// App context
// ---------------------------------------------------------------------------

type ReminderOverlay = "reminder" | null;
type PremiumFeature = "grammar_lens" | "immersion" | "dual_subtitles";

interface AppCtx {
  username: string;
  screen: Screen;
  navigateTo: (s: Screen, opts?: { settingsMode?: SettingsMode }) => void;
  settingsMode: SettingsMode;
  reminderOpen: ReminderOverlay;
  openReminder: () => void;
  closeReminder: () => void;
  openTraining: () => void;
  openLesson: (topic: string) => void;
  requirePremiumFeature: (feature: PremiumFeature, featureName: string) => Promise<boolean>;
  openSubscription: (intent?: SubscriptionIntent) => void;
  targetLang: string;
  nativeLang: string;
  setLangPair: (targetLang: string, nativeLang: string) => void;
  /** Clear local credentials and return to onboarding (login/new profile). */
  signOut: () => Promise<void>;
}

const AppContext = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Sidebar / topbar (app shell)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

type ObStep = "native_lang" | "username" | "target_lang" | "level_setup";

// ---------------------------------------------------------------------------
// Resumable UI state — the browser closes the action popup on ANY focus loss
// (a click outside, another window, waiting out a long translation), wiping
// all React state. A session-scoped snapshot lets the next open resume on the
// same screen / onboarding step instead of starting over.
// ---------------------------------------------------------------------------

const UI_STATE_KEY = "vk_ui_state";
// Stale snapshots are ignored: resuming mid-onboarding seconds after an
// accidental close is helpful; jumping to a day-old screen is confusing.
const UI_STATE_TTL_MS = 15 * 60 * 1000;

interface SavedObState {
  step: ObStep;
  nativeLang: string;
  username: string;
  displayName: string;
  targetLangs: string[];
  levelSetup: Record<string, { level: string; goals: string; prompt: string }>;
  levelIndex: number;
}

interface SavedUiState {
  ts: number;
  screen: Screen;
  settingsMode: SettingsMode;
  /** Present only while the onboarding flow is active. */
  ob?: SavedObState;
}

interface GoogleSigninHandoff {
  username: string;
  display_name: string;
  created: boolean;
  ts: number;
}

async function loadSavedUiState(): Promise<SavedUiState | null> {
  try {
    const stored = await sessionGet([UI_STATE_KEY]);
    const state = stored[UI_STATE_KEY] as SavedUiState | undefined;
    if (!state?.ts || Date.now() - state.ts > UI_STATE_TTL_MS) return null;
    return state;
  } catch {
    return null;
  }
}

export default function App() {
  const { t, switchLanguage } = useI18n();

  // undefined = still checking storage; null = no user (show onboarding)
  const [username, setUsername] = useState<string | null | undefined>(undefined);
  const [screen, setScreen] = useState<Screen>("home");
  const [settingsMode, setSettingsMode] = useState<SettingsMode>("onboarding");
  const [reminderOpen, setReminderOpen] = useState<ReminderOverlay>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [billing, setBilling] = useState<api.BillingStatus | null>(null);
  const [premiumPrompt, setPremiumPrompt] = useState<{ feature: PremiumFeature; featureName: string } | null>(null);
  const [subscriptionIntent, setSubscriptionIntent] = useState<SubscriptionIntent>({ mode: "new" });
  const webShortcutHandled = useRef(false);
  const [initialRouteReady, setInitialRouteReady] = useState(false);

  useEffect(() => {
    if (!toastMsg) return;
    const timer = setTimeout(() => setToastMsg(null), 3500);
    return () => clearTimeout(timer);
  }, [toastMsg]);

  useEffect(() => {
    if (!username) return;
    api.getBillingStatus().then(setBilling).catch(() => setBilling(null));
  }, [username]);

  useEffect(() => {
    if (!username) return;
    void sendToActiveTab({ type: "VEKSHA_PING" });
  }, [username]);

  const detected = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  const [targetLang, setTargetLang] = useState("en");
  const [nativeLang, setNativeLang] = useState(detected);

  // Onboarding sub-steps (only used when username === null)
  const [obStep, setObStep] = useState<ObStep>("native_lang");
  const [pendingNativeLang, setPendingNativeLang] = useState(detected);
  const [pendingUsername, setPendingUsername] = useState("");
  const [pendingDisplayName, setPendingDisplayName] = useState("");
  // A fresh profile must make an explicit first choice. Preselecting English
  // made a click on another language add it *after* English, so the UI showed
  // two learning languages and kept English active.
  const [pendingTargetLangs, setPendingTargetLangs] = useState<string[]>([]);
  const [pendingLevelSetup, setPendingLevelSetup] = useState<Record<string, { level: string; goals: string; prompt: string }>>({});
  const [pendingLevelIndex, setPendingLevelIndex] = useState(0);

  const setLangPair = useCallback((tl: string, nl: string) => {
    setTargetLang(tl);
    setNativeLang(nl);
  }, []);

  useEffect(() => {
    Promise.all([
      storageGet([
        CONFIG.STORAGE_KEY_USERNAME,
        CONFIG.STORAGE_KEY_TOKEN,
        CONFIG.STORAGE_KEY_GOOGLE_SIGNIN_RESULT,
      ]),
      loadSavedUiState(),
    ]).then(async ([result, saved]) => {
      const stored = result[CONFIG.STORAGE_KEY_USERNAME] as string | undefined;
      const token = result[CONFIG.STORAGE_KEY_TOKEN] as string | undefined;
      const googleHandoff = result[CONFIG.STORAGE_KEY_GOOGLE_SIGNIN_RESULT] as GoogleSigninHandoff | undefined;
      if (stored && token) api.setAuthToken(token);
      // OAuth runs in the background and opening its tab usually destroys the
      // action popup. Consume the background handoff before the stale
      // pre-OAuth onboarding snapshot, otherwise an authenticated user lands
      // back on the name form and can accidentally create a second profile.
      if (
        stored && token && googleHandoff?.username === stored &&
        Date.now() - googleHandoff.ts <= UI_STATE_TTL_MS
      ) {
        await storageRemove([CONFIG.STORAGE_KEY_GOOGLE_SIGNIN_RESULT]);
        if (googleHandoff.created) {
          if (saved?.ob) {
            setPendingNativeLang(saved.ob.nativeLang);
            setNativeLang(saved.ob.nativeLang);
            setPendingTargetLangs(saved.ob.targetLangs ?? []);
          }
          setPendingUsername(stored);
          setPendingDisplayName(googleHandoff.display_name);
          setObStep("target_lang");
          setUsername(null);
          return;
        }
        setUsername(stored);
        await routeAfterUsername(stored);
        return;
      }
      if (googleHandoff) {
        await storageRemove([CONFIG.STORAGE_KEY_GOOGLE_SIGNIN_RESULT]);
      }
      // A popup killed mid-onboarding: resume the same step with the pending
      // choices instead of restarting from scratch. Credentials may already
      // exist (registration happens at the username step), so this must be
      // checked before the signed-in route.
      if (saved?.ob && !(stored && token && saved.ob.step === "username" && !saved.ob.username)) {
        const ob = saved.ob;
        setPendingNativeLang(ob.nativeLang);
        setNativeLang(ob.nativeLang);
        setPendingUsername(ob.username);
        setPendingDisplayName(ob.displayName);
        setPendingTargetLangs(ob.targetLangs ?? []);
        setPendingLevelSetup(ob.levelSetup ?? {});
        setPendingLevelIndex(ob.levelIndex ?? 0);
        setObStep(ob.step);
        setUsername(null);
        return;
      }
      if (stored && token) {
        setUsername(stored);
        await routeAfterUsername(stored, saved);
      } else {
        setUsername(null); // show onboarding flow (also covers pre-auth installs)
      }
    });
  }, []);

  // Snapshot the resumable UI state on every change. Skipped until the initial
  // storage read resolves so the default "home" doesn't clobber a saved
  // snapshot before it has been restored.
  useEffect(() => {
    if (username === undefined) return;
    const state: SavedUiState = {
      ts: Date.now(),
      screen,
      settingsMode,
      ...(username === null
        ? {
            ob: {
              step: obStep,
              nativeLang: pendingNativeLang,
              username: pendingUsername,
              displayName: pendingDisplayName,
              targetLangs: pendingTargetLangs,
              levelSetup: pendingLevelSetup,
              levelIndex: pendingLevelIndex,
            },
          }
        : {}),
    };
    sessionSet({ [UI_STATE_KEY]: state });
  }, [username, screen, settingsMode, obStep, pendingNativeLang, pendingUsername, pendingDisplayName, pendingTargetLangs, pendingLevelSetup, pendingLevelIndex]);

  async function routeAfterUsername(name: string, saved?: SavedUiState | null) {
    try {
      const settings = await api.getSettings(name);
      if (settings.native_lang) {
        setNativeLang(settings.native_lang);
        switchLanguage(settings.native_lang).catch(() => {});
      }
      if (settings.target_lang) setTargetLang(settings.target_lang);
      if (!settings.is_onboarded) {
        setSettingsMode("onboarding");
        setScreen("settings");
      } else if (saved) {
        // Reopened shortly after a focus-loss close — resume where they were.
        setSettingsMode(saved.settingsMode);
        // Resume useful destinations while retiring names from previous UI models.
        const previousScreen = saved.screen as string;
        setScreen(
          previousScreen === "chat"
            ? "translator"
            : previousScreen === "topics"
              ? "goals"
              : saved.screen,
        );
      } else {
        setScreen("home");
      }
      setInitialRouteReady(true);
    } catch (err) {
      // Stale credentials (account wiped server-side) — back to onboarding.
      if (String((err as Error).message).includes("HTTP 401")) {
        await signOut();
        return;
      }
      setScreen("home");
      setInitialRouteReady(true);
    }
  }

  // Step 1: native language selected → wait for translation → show username screen
  async function handleNativeLangSelected(lang: string): Promise<void> {
    setPendingNativeLang(lang);
    setNativeLang(lang);
    storageSet({ [CONFIG.STORAGE_KEY_NATIVE_LANG]: lang });
    await switchLanguage(lang);
    setObStep("username");
  }

  // Step 2: username entered → register on the backend → store token → next step
  async function handleUsernameEntered(name: string) {
    if (pendingUsername) {
      setPendingDisplayName(name);
      setObStep("target_lang");
      return;
    }
    const { username: registered, token } = await api.register(name);
    api.setAuthToken(token);
    await storageSet({
      [CONFIG.STORAGE_KEY_USERNAME]: registered,
      [CONFIG.STORAGE_KEY_TOKEN]: token,
    });
    setPendingUsername(registered);
    setPendingDisplayName(name);
    setObStep("target_lang");
  }

  // Sign out: forget local credentials and restart the onboarding flow,
  // which doubles as the login screen (Google or a fresh profile).
  async function signOut() {
    await storageRemove([CONFIG.STORAGE_KEY_USERNAME, CONFIG.STORAGE_KEY_TOKEN]);
    api.setAuthToken(null);
    // Clear pending onboarding leftovers: a stale pendingUsername would make
    // the username step skip registration for the signed-out account.
    setPendingUsername("");
    setPendingDisplayName("");
    setPendingTargetLangs([]);
    setPendingLevelSetup({});
    setPendingLevelIndex(0);
    setObStep("native_lang");
    setScreen("home");
    setUsername(null);
  }

  // Step 2 alternative: Google sign-in. The OAuth flow runs in the background
  // (the popup dies when the auth window takes focus); if this popup survives,
  // continue in place — a brand-new account proceeds with onboarding, an
  // existing one goes to its usual screen. If the popup died, the background
  // has already persisted the credentials and the next open picks them up.
  async function handleGoogleSignIn() {
    if (!isExtension) {
      const resp = await googleSignIn();
      api.setAuthToken(resp.token);
      await storageSet({
        [CONFIG.STORAGE_KEY_USERNAME]: resp.username,
        [CONFIG.STORAGE_KEY_TOKEN]: resp.token,
      });
      if (resp.created) {
        setPendingUsername(resp.username);
        setPendingDisplayName(resp.display_name);
        setObStep("target_lang");
        return;
      }
      setUsername(resp.username);
      await routeAfterUsername(resp.username);
      return;
    }
    const resp = (await chrome.runtime.sendMessage({ type: "VEKSHA_GOOGLE_SIGNIN" })) as
      | { ok: true; username: string; display_name: string; created: boolean }
      | { ok: false; error: string }
      | undefined;
    if (!resp) throw new Error("google-cancelled"); // popup lost the response
    if (!resp.ok) throw new Error(resp.error);
    await storageRemove([CONFIG.STORAGE_KEY_GOOGLE_SIGNIN_RESULT]);
    const st = await storageGet([CONFIG.STORAGE_KEY_TOKEN]);
    api.setAuthToken((st[CONFIG.STORAGE_KEY_TOKEN] as string) || null);
    if (resp.created) {
      setPendingUsername(resp.username);
      setPendingDisplayName(resp.display_name);
      setObStep("target_lang");
      return;
    }
    setUsername(resp.username);
    await routeAfterUsername(resp.username);
  }

  // Step 3: target language selected → go to level/goals setup
  async function handleTargetLangSelected(langs: string[]) {
    setTargetLang(langs[0]);
    setPendingTargetLangs(langs);
    setPendingLevelIndex(0);
    setObStep("level_setup");
  }

  // Step 4: level/goals/prompt entered → save settings → enter app
  async function handleLevelSetupComplete(opts: { level: string; goals: string; prompt: string }) {
    const lang = pendingTargetLangs[pendingLevelIndex];
    const languageSettings = { ...pendingLevelSetup, [lang]: opts };
    setPendingLevelSetup(languageSettings);
    if (pendingLevelIndex < pendingTargetLangs.length - 1) {
      setPendingLevelIndex((index) => index + 1);
      return;
    }
    const saved = await api.saveSettings(pendingUsername, {
      englishLevel: opts.level,
      goals: opts.goals,
      generalPrompt: opts.prompt,
      displayName: pendingDisplayName,
      nativeLang: pendingNativeLang,
      targetLang: pendingTargetLangs[0],
      targetLangs: pendingTargetLangs,
      languageSettings,
    });
    // The backend is the source of truth for filtering/order. Do not enter the
    // app with optimistic language state when saving failed or was normalized.
    setLangPair(saved.target_lang, saved.native_lang);
    setUsername(pendingUsername);
    setScreen("home");
    setInitialRouteReady(true);
  }

  const navigateTo = useCallback((s: Screen, opts?: { settingsMode?: SettingsMode }) => {
    if (opts?.settingsMode) setSettingsMode(opts.settingsMode);
    setScreen(s);
  }, []);

  const requirePremiumFeature = useCallback(async (
    feature: PremiumFeature,
    featureName: string,
  ): Promise<boolean> => {
    let current = billing;
    if (!current) {
      try {
        current = await api.getBillingStatus();
        setBilling(current);
      } catch {
        // Let the server remain the source of truth when status is temporarily
        // unavailable instead of locking a paid user out on a network error.
        return true;
      }
    }
    if (current.features.includes(feature)) return true;
    setPremiumPrompt({ feature, featureName });
    return false;
  }, [billing]);

  const openSubscription = useCallback((intent: SubscriptionIntent = { mode: "new" }) => {
    setPremiumPrompt(null);
    setSubscriptionIntent(intent);
    setScreen("subscription");
  }, []);

  const openReminder = useCallback(() => setReminderOpen("reminder"), []);
  const closeReminder = useCallback(() => setReminderOpen(null), []);

  // On the web the study windows render as local overlays; in the extension
  // they are injected into the active tab so they outlive the popup.
  const [webOverlay, setWebOverlay] = useState<
    { kind: "training" } | { kind: "lesson"; topic: string } | null
  >(null);

  const openTraining = useCallback(async () => {
    if (!isExtension) { setWebOverlay({ kind: "training" }); return; }
    const status = await sendToActiveTab({ type: "VEKSHA_OPEN_TRAINING", username });
    if (status === "restricted") setToastMsg("Open any webpage first, then try Training again.");
    else if (status === "error") setToastMsg("Could not open Training. Please refresh the page.");
    // Opened on the page — collapse the popup so it's out of the way.
    else window.close();
  }, [username]);

  const openLesson = useCallback(async (topic: string) => {
    if (!isExtension) { setWebOverlay({ kind: "lesson", topic }); return; }
    const status = await sendToActiveTab({ type: "VEKSHA_OPEN_LESSON", username, topic });
    if (status === "restricted") setToastMsg("Open any webpage first, then try Lesson again.");
    else if (status === "error") setToastMsg("Could not open Lesson. Please refresh the page.");
    else window.close();
  }, [username]);

  useEffect(() => {
    if (isExtension || !username || !initialRouteReady || webShortcutHandled.current) return;
    webShortcutHandled.current = true;
    const action = new URLSearchParams(window.location.search).get("open");
    if (action === "dictionary") setScreen("dictionary");
    if (action === "training") void openTraining();
  }, [username, initialRouteReady, openTraining]);

  // Still checking storage — render nothing to avoid flash
  if (username === undefined) {
    return <div className="app" />;
  }

  // New user — welcome + 4-step onboarding
  if (username === null) {
    return (
      <div className="app">
        {obStep === "native_lang" && (
          <NativeLangScreen initialLang={pendingNativeLang} onContinue={handleNativeLangSelected} />
        )}
        {obStep === "username" && (
          <OnboardingScreen
            initialName={pendingDisplayName}
            onComplete={handleUsernameEntered}
            onGoogle={CONFIG.GOOGLE_CLIENT_ID ? handleGoogleSignIn : undefined}
            onBack={() => setObStep("native_lang")}
          />
        )}
        {obStep === "target_lang" && (
          <TargetLangScreen
            nativeLang={pendingNativeLang}
            initialLangs={pendingTargetLangs}
            onContinue={handleTargetLangSelected}
            onBack={() => setObStep("username")}
          />
        )}
        {obStep === "level_setup" && (
          <LevelSetupScreen
            key={pendingTargetLangs[pendingLevelIndex]}
            targetLang={pendingTargetLangs[pendingLevelIndex]}
            initialValues={pendingLevelSetup[pendingTargetLangs[pendingLevelIndex]]}
            onComplete={handleLevelSetupComplete}
            onBack={() => pendingLevelIndex > 0
              ? setPendingLevelIndex((index) => index - 1)
              : setObStep("target_lang")}
          />
        )}
      </div>
    );
  }

  const ctx: AppCtx = {
    username,
    screen,
    navigateTo,
    settingsMode,
    reminderOpen,
    openReminder,
    closeReminder,
    openTraining,
    openLesson,
    requirePremiumFeature,
    openSubscription,
    targetLang,
    nativeLang,
    setLangPair,
    signOut,
  };

  const pageMeta: Record<string, { title: string; sub: string }> = {
    home: { title: "veksha", sub: "" },
    translator: { title: t.translator_title, sub: "" },
    goals: { title: t.lesson_goals_kicker, sub: t.lesson_goals_hint },
    statistics: { title: t.nav_stats, sub: t.sub_stats },
    dictionary: { title: t.dictionary_title, sub: "" },
    immersion: { title: t.nav_immersion, sub: "" },
    myWords: { title: t.my_words_title, sub: "" },
    quizlet: { title: "Quizlet", sub: "" },
    settings: { title: t.nav_settings, sub: t.sub_settings },
    subscription: { title: t.subscription_title, sub: "" },
    debug: { title: t.debug_title, sub: "" },
  };
  const meta = pageMeta[screen] ?? pageMeta.home;

  return (
    <AppContext.Provider value={ctx}>
      <div className={`app${isExtension ? "" : " app-web"}`}>
        <div className="workspace-frame">
          <div className="workspace-header">
            {screen !== "home" && (
              <button
                className="workspace-back"
                aria-label="Back"
                onClick={() => navigateTo(
                  screen === "subscription" && subscriptionIntent.mode !== "add" ? "settings" : "home",
                )}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5M12 19l-7-7 7-7" />
                </svg>
              </button>
            )}
            {screen === "home" && <div className="workspace-mark" aria-hidden="true" />}
            <div className="workspace-title">{meta.title}</div>
            {screen === "home" && <span className="workspace-context">{targetLang.toUpperCase()}</span>}
            {screen === "home" && __DEV_BUILD__ && (
              <>
                <div className="workspace-header-spacer" />
                <button className="workspace-debug" onClick={() => navigateTo("debug")} aria-label={t.debug_title}>&#9881;&#65038;</button>
              </>
            )}
          </div>

          <div className="workspace-content">
            {screen === "home" && <HomeScreen />}
            {screen === "translator" && <TranslatorScreen />}
            {screen === "goals" && <LearningGoalsScreen />}
            {screen === "dictionary" && <DictionaryScreen />}
            {screen === "immersion" && <ImmersionScreen />}
            {screen === "myWords" && <MyWordsScreen />}
            {screen === "settings" && <SettingsScreen />}
            {screen === "subscription" && (
              <SubscriptionScreen intent={subscriptionIntent} onStatusChange={setBilling} />
            )}
            {screen === "statistics" && <StatisticsScreen />}
            {screen === "quizlet" && <QuizletScreen />}
            {screen === "debug" && __DEV_BUILD__ && <DebugScreen />}
          </div>
        </div>

        {!isExtension && (
          <nav className="web-bottom-nav" aria-label="Primary navigation">
            <button className={screen === "home" ? "is-active" : ""} onClick={() => navigateTo("home")}>
              <span aria-hidden="true">⌂</span><small>Veksha</small>
            </button>
            <button className={screen === "dictionary" ? "is-active" : ""} onClick={() => navigateTo("dictionary")}>
              <span aria-hidden="true">Aa</span><small>{t.dictionary_title}</small>
            </button>
            <button onClick={openTraining}>
              <span className="web-nav-practice" aria-hidden="true">↻</span><small>{t.nav_training}</small>
            </button>
            <button className={screen === "translator" ? "is-active" : ""} onClick={() => navigateTo("translator")}>
              <span aria-hidden="true">文</span><small>{t.translator_title}</small>
            </button>
            <button className={screen === "settings" ? "is-active" : ""} onClick={() => navigateTo("settings", { settingsMode: "menu" })}>
              <span aria-hidden="true">⚙</span><small>{t.nav_settings}</small>
            </button>
          </nav>
        )}

        {reminderOpen === "reminder" && <ReminderCard />}

        {webOverlay?.kind === "training" && (
          <TrainingWindow username={username} onClose={() => setWebOverlay(null)} />
        )}
        {webOverlay?.kind === "lesson" && (
          <LessonWindow
            username={username}
            topicName={webOverlay.topic}
            onClose={() => setWebOverlay(null)}
          />
        )}

        {premiumPrompt && (
          <div className="imm-modal-backdrop">
            <div className="imm-modal premium-modal" role="dialog" aria-modal="true" aria-labelledby="premium-required-title">
              <div className="imm-modal-icon premium-modal-icon" aria-hidden="true">★</div>
              <h3 id="premium-required-title">{t.premium_required_title}</h3>
              <p className="imm-modal-sub">
                {t.premium_required_desc.replace("{feature}", premiumPrompt.featureName)}
              </p>
              <div className="premium-modal-actions">
                <button
                  className="btn btn-gradient"
                  onClick={() => openSubscription({ mode: "add", feature: premiumPrompt.feature })}
                >
                  {t.common_yes}
                </button>
                <button className="btn" onClick={() => setPremiumPrompt(null)}>{t.common_no}</button>
              </div>
            </div>
          </div>
        )}

        {toastMsg && <div className="toast">{toastMsg}</div>}
      </div>
    </AppContext.Provider>
  );
}
