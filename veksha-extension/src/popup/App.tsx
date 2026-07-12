import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import * as api from "../shared/api";
import { CONFIG } from "../shared/config";
import { useI18n } from "../shared/i18n";
import { isExtension, storageGet, storageRemove, storageSet } from "../shared/platform";
import type { Screen, SettingsMode } from "../shared/types";
import { LessonWindow } from "./overlays/LessonWindow";
import { ReminderCard } from "./overlays/ReminderCard";
import { TopicPickerOverlay } from "./overlays/TopicPickerOverlay";
import { TrainingWindow } from "./overlays/TrainingWindow";
import { ChatScreen } from "./screens/ChatScreen";
import { HomeScreen } from "./screens/HomeScreen";
import { ImmersionScreen } from "./screens/ImmersionScreen";
import { DebugScreen } from "./screens/DebugScreen";
import { DictionaryScreen } from "./screens/DictionaryScreen";
import { LevelSetupScreen } from "./screens/LevelSetupScreen";
import { NativeLangScreen } from "./screens/NativeLangScreen";
import { OnboardingScreen } from "./screens/OnboardingScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { StatisticsScreen } from "./screens/StatisticsScreen";
import { TargetLangScreen } from "./screens/TargetLangScreen";
import { TopicsScreen } from "./screens/TopicsScreen";
import { TourScreen } from "./screens/TourScreen";

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

interface AppCtx {
  username: string;
  screen: Screen;
  navigateTo: (s: Screen, opts?: { settingsMode?: SettingsMode }) => void;
  settingsMode: SettingsMode;
  reminderOpen: ReminderOverlay;
  openReminder: () => void;
  closeReminder: () => void;
  openTraining: () => void;
  openLessonPicker: () => void;
  openLesson: (topic: string) => void;
  targetLang: string;
  nativeLang: string;
  setLangPair: (targetLang: string, nativeLang: string) => void;
  /** Clear local credentials and return to onboarding (login/new profile). */
  signOut: () => Promise<void>;
  /** Jump to the chat screen and send this text as the first message. */
  sendToChat: (text: string) => void;
  /** ChatScreen picks up a pending home-screen message (once). */
  takePendingChat: () => string | null;
  takeVoiceResume: () => string | null;
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

export default function App() {
  const { t, switchLanguage } = useI18n();

  // undefined = still checking storage; null = no user (show onboarding)
  const [username, setUsername] = useState<string | null | undefined>(undefined);
  const [screen, setScreen] = useState<Screen>("home");
  const [settingsMode, setSettingsMode] = useState<SettingsMode>("onboarding");
  const [reminderOpen, setReminderOpen] = useState<ReminderOverlay>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  // Help bubble — pops up on the chat screen, dismissed by any click outside it.
  const [helpVisible, setHelpVisible] = useState(true);
  const helpRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!toastMsg) return;
    const timer = setTimeout(() => setToastMsg(null), 3500);
    return () => clearTimeout(timer);
  }, [toastMsg]);

  const detected = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  const [targetLang, setTargetLang] = useState("en");
  const [nativeLang, setNativeLang] = useState(detected);

  // Onboarding sub-steps (only used when username === null)
  const [obStep, setObStep] = useState<ObStep>("native_lang");
  // Post-registration tour (8 animated scenes)
  const [showTour, setShowTour] = useState(false);
  // Message typed on the home screen, delivered to ChatScreen on mount.
  const pendingChatRef = useRef<string | null>(null);
  const voiceResumeRef = useRef<string | null>(null);
  const [pendingNativeLang, setPendingNativeLang] = useState(detected);
  const [pendingUsername, setPendingUsername] = useState("");
  const [pendingDisplayName, setPendingDisplayName] = useState("");
  const [pendingTargetLangs, setPendingTargetLangs] = useState<string[]>(["en"]);
  const [pendingLevelSetup, setPendingLevelSetup] = useState<Record<string, { level: string; goals: string; prompt: string }>>({});
  const [pendingLevelIndex, setPendingLevelIndex] = useState(0);

  const setLangPair = useCallback((tl: string, nl: string) => {
    setTargetLang(tl);
    setNativeLang(nl);
  }, []);

  useEffect(() => {
    storageGet([CONFIG.STORAGE_KEY_USERNAME, CONFIG.STORAGE_KEY_TOKEN, "vk_voice_resume"]).then(
      async (result: Record<string, unknown>) => {
        const stored = result[CONFIG.STORAGE_KEY_USERNAME] as string | undefined;
        const token = result[CONFIG.STORAGE_KEY_TOKEN] as string | undefined;
        if (stored && token) {
          api.setAuthToken(token);
          setUsername(stored);
          await routeAfterUsername(stored);
          const resumeTarget = result.vk_voice_resume as string | undefined;
          if (resumeTarget) {
            voiceResumeRef.current = resumeTarget;
            await storageRemove(["vk_voice_resume"]);
            if (resumeTarget === "dictionary_cards") setScreen("dictionary");
            else if (resumeTarget === "chat") setScreen("chat");
            else setScreen("home");
          }
        } else {
          setUsername(null); // show onboarding flow (also covers pre-auth installs)
        }
      }
    );
  }, []);

  async function routeAfterUsername(name: string) {
    try {
      const settings = await api.getSettings(name);
      storageSet({ [`vk_voice_enabled_${name}`]: settings.voice_enabled ?? true });
      if (settings.native_lang) {
        setNativeLang(settings.native_lang);
        switchLanguage(settings.native_lang).catch(() => {});
      }
      if (settings.target_lang) setTargetLang(settings.target_lang);
      if (!settings.is_onboarded) {
        setSettingsMode("onboarding");
        setScreen("settings");
      } else {
        setScreen("home");
      }
    } catch (err) {
      // Stale credentials (account wiped server-side) — back to onboarding.
      if (String((err as Error).message).includes("HTTP 401")) {
        await signOut();
        return;
      }
      setScreen("home");
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
    const resp = (await chrome.runtime.sendMessage({ type: "VEKSHA_GOOGLE_SIGNIN" })) as
      | { ok: true; username: string; created: boolean }
      | { ok: false; error: string }
      | undefined;
    if (!resp) throw new Error("google-cancelled"); // popup lost the response
    if (!resp.ok) throw new Error(resp.error);
    const st = await storageGet([CONFIG.STORAGE_KEY_TOKEN]);
    api.setAuthToken((st[CONFIG.STORAGE_KEY_TOKEN] as string) || null);
    if (resp.created) {
      setPendingUsername(resp.username);
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
    try {
      await api.saveSettings(pendingUsername, {
        englishLevel: opts.level,
        goals: opts.goals,
        generalPrompt: opts.prompt,
        displayName: pendingDisplayName,
        nativeLang: pendingNativeLang,
        targetLang: pendingTargetLangs[0],
        targetLangs: pendingTargetLangs,
        languageSettings,
      });
    } catch { /* ignore — user can update in Settings later */ }
    setLangPair(pendingTargetLangs[0], pendingNativeLang);
    setUsername(pendingUsername);
    setScreen("home");
    setShowTour(true); // the animated tour runs right after registration
  }

  const startTour = useCallback(() => {
    setHelpVisible(false);
    setShowTour(true);
  }, []);

  // Any click that lands outside the help bubble dismisses it.
  const handleAppClick = useCallback((e: React.MouseEvent) => {
    if (helpRef.current && !helpRef.current.contains(e.target as Node)) {
      setHelpVisible(false);
    }
  }, []);

  const navigateTo = useCallback((s: Screen, opts?: { settingsMode?: SettingsMode }) => {
    if (opts?.settingsMode) setSettingsMode(opts.settingsMode);
    setScreen(s);
  }, []);

  const openReminder = useCallback(() => setReminderOpen("reminder"), []);
  const closeReminder = useCallback(() => setReminderOpen(null), []);

  // On the web the study windows render as local overlays; in the extension
  // they are injected into the active tab so they outlive the popup.
  const [webOverlay, setWebOverlay] = useState<
    { kind: "training" } | { kind: "picker" } | { kind: "lesson"; topic: string } | null
  >(null);

  const openTraining = useCallback(async () => {
    if (!isExtension) { setWebOverlay({ kind: "training" }); return; }
    const status = await sendToActiveTab({ type: "VEKSHA_OPEN_TRAINING", username });
    if (status === "restricted") setToastMsg("Open any webpage first, then try Training again.");
    else if (status === "error") setToastMsg("Could not open Training. Please refresh the page.");
    // Opened on the page — collapse the popup so it's out of the way.
    else window.close();
  }, [username]);

  const openLessonPicker = useCallback(async () => {
    if (!isExtension) { setWebOverlay({ kind: "picker" }); return; }
    const status = await sendToActiveTab({ type: "VEKSHA_OPEN_LESSON_PICKER", username });
    if (status === "restricted") setToastMsg("Open any webpage first, then try Lesson again.");
    else if (status === "error") setToastMsg("Could not open Lesson. Please refresh the page.");
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
            onGoogle={isExtension && CONFIG.GOOGLE_CLIENT_ID ? handleGoogleSignIn : undefined}
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
    openLessonPicker,
    openLesson,
    targetLang,
    nativeLang,
    setLangPair,
    signOut,
    sendToChat: (text: string) => {
      pendingChatRef.current = text;
      navigateTo("chat");
    },
    takePendingChat: () => {
      const text = pendingChatRef.current;
      pendingChatRef.current = null;
      return text;
    },
    takeVoiceResume: () => {
      const target = voiceResumeRef.current;
      voiceResumeRef.current = null;
      return target;
    },
  };

  const pageMeta: Record<string, { title: string; sub: string }> = {
    home: { title: "veksha", sub: "" },
    chat: { title: t.nav_assistant, sub: t.sub_assistant },
    topics: { title: t.nav_topics, sub: t.sub_topics },
    statistics: { title: t.nav_stats, sub: t.sub_stats },
    dictionary: { title: t.dictionary_title, sub: "" },
    immersion: { title: t.nav_immersion, sub: "" },
    settings: { title: t.nav_settings, sub: t.sub_settings },
    debug: { title: t.debug_title, sub: "" },
  };
  const meta = pageMeta[screen] ?? pageMeta.home;

  return (
    <AppContext.Provider value={ctx}>
      <div className="app" onClick={handleAppClick}>
        <div className="shell-main">
          <div className="shell-topbar">
            {screen !== "home" && (
              <button className="m-back" aria-label="Back" onClick={() => navigateTo("home")}>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 12H5M12 19l-7-7 7-7" />
                </svg>
              </button>
            )}
            <div className="shell-page-title">{meta.title}</div>
            {screen === "home" && __DEV_BUILD__ && (
              <>
                <div className="shell-topbar-spacer" />
                <button className="m-debug" onClick={() => navigateTo("debug")} aria-label={t.debug_title}>&#9881;&#65038;</button>
              </>
            )}
          </div>

          <div className="shell-content">
            {screen === "home" && <HomeScreen />}
            {screen === "chat" && <ChatScreen />}
            {screen === "topics" && <TopicsScreen />}
            {screen === "dictionary" && <DictionaryScreen />}
            {screen === "immersion" && <ImmersionScreen />}
            {screen === "settings" && <SettingsScreen />}
            {screen === "statistics" && <StatisticsScreen />}
            {screen === "debug" && __DEV_BUILD__ && <DebugScreen />}
          </div>
        </div>

        {showTour && <TourScreen onFinish={() => setShowTour(false)} />}

        {screen === "chat" && helpVisible && !showTour && (
          <div className="help-bubble" ref={helpRef}>
            <div className="help-bubble-row">
              <div className="help-bubble-icon">🪄</div>
              <div className="help-bubble-text">
                <strong className="help-bubble-title">{t.help_title}</strong>
                <span className="help-bubble-sub">{t.help_body}</span>
              </div>
            </div>
            <button className="btn btn-gradient help-bubble-btn" onClick={startTour}>
              {t.help_start}
            </button>
          </div>
        )}

        {reminderOpen === "reminder" && <ReminderCard />}

        {webOverlay?.kind === "training" && (
          <TrainingWindow username={username} onClose={() => setWebOverlay(null)} />
        )}
        {webOverlay?.kind === "picker" && (
          <TopicPickerOverlay
            username={username}
            onSelect={(topic) => setWebOverlay({ kind: "lesson", topic })}
            onClose={() => setWebOverlay(null)}
          />
        )}
        {webOverlay?.kind === "lesson" && (
          <LessonWindow
            username={username}
            topicName={webOverlay.topic}
            onClose={() => setWebOverlay(null)}
          />
        )}

        {toastMsg && <div className="toast">{toastMsg}</div>}
      </div>
    </AppContext.Provider>
  );
}
