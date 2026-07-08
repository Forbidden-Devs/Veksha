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
import { DebugScreen } from "./screens/DebugScreen";
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

const NavIcons = {
  assistant: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  topics: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  ),
  training: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
    </svg>
  ),
  stats: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" /><path d="M7 14l3-4 3 3 4-6" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
};

/** Per-user key for "the immersion explainer was dismissed". Global-per-device
 *  would hide the explainer from a second account on the same machine. */
const immersionExplainedKey = (username: string) => `vk_immersion_explained_${username}`;

/** Immersion toggle as a sidebar item. Every enable shows the explainer modal
 *  until the user opts out with "I already know". */
function SidebarImmersion({ username, onExplain }: { username: string; onExplain: () => void }) {
  const t = useI18n().t;
  const [on, setOn] = useState(false);

  useEffect(() => {
    storageGet([CONFIG.STORAGE_KEY_IMMERSION]).then((res) => {
      setOn(Boolean(res[CONFIG.STORAGE_KEY_IMMERSION]));
    });
  }, []);

  async function toggle() {
    const next = !on;
    setOn(next);
    storageSet({ [CONFIG.STORAGE_KEY_IMMERSION]: next });
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) await chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_TOGGLE_IMMERSION", enabled: next });
    } catch { /* no content script on this tab — state is still saved */ }
    if (next) {
      const key = immersionExplainedKey(username);
      const st = await storageGet([key]);
      if (!st[key]) onExplain();
    }
  }

  return (
    <button className={`shell-nav-item${on ? " active" : ""}`} onClick={toggle} title={t.immersion_hint}>
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2l1.5 4.2L18 8l-4.5 1.8L12 14l-1.5-4.2L6 8l4.5-1.8z" />
        <path d="M18.5 13l.9 2.4 2.6 1-2.6 1-.9 2.6-.9-2.6-2.6-1 2.6-1z" />
      </svg>
      {t.nav_immersion}
    </button>
  );
}

function SidebarWordCount({ username }: { username: string }) {
  const t = useI18n().t;
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    api.getKbSummary(username)
      .then((s) => setCount(s.learning_count + s.known_count))
      .catch(() => {});
  }, [username]);
  if (count === null) return null;
  const text = t.sidebar_collected.replace("{n}", "").trim();
  return (
    <div className="shell-side-foot">
      <div className="shell-streak">
        <div className="num">{count}</div>
        <div>{text}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

type ObStep = "native_lang" | "username" | "target_lang" | "level_setup";

export default function App() {
  const { t, switchLanguage } = useI18n();

  // undefined = still checking storage; null = no user (show onboarding)
  const [username, setUsername] = useState<string | null | undefined>(undefined);
  const [screen, setScreen] = useState<Screen>("chat");
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
  // Immersion explainer modal — shown on every enable until "I already know"
  const [immModal, setImmModal] = useState(false);
  const [pendingNativeLang, setPendingNativeLang] = useState(detected);
  const [pendingUsername, setPendingUsername] = useState("");
  const [pendingTargetLang, setPendingTargetLang] = useState("en");

  const setLangPair = useCallback((tl: string, nl: string) => {
    setTargetLang(tl);
    setNativeLang(nl);
  }, []);

  useEffect(() => {
    storageGet([CONFIG.STORAGE_KEY_USERNAME, CONFIG.STORAGE_KEY_TOKEN]).then(
      (result: Record<string, unknown>) => {
        const stored = result[CONFIG.STORAGE_KEY_USERNAME] as string | undefined;
        const token = result[CONFIG.STORAGE_KEY_TOKEN] as string | undefined;
        if (stored && token) {
          api.setAuthToken(token);
          setUsername(stored);
          routeAfterUsername(stored);
        } else {
          setUsername(null); // show onboarding flow (also covers pre-auth installs)
        }
      }
    );
  }, []);

  async function routeAfterUsername(name: string) {
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
      } else {
        setScreen("chat");
      }
    } catch (err) {
      // Stale credentials (account wiped server-side) — back to onboarding.
      if (String((err as Error).message).includes("HTTP 401")) {
        await signOut();
        return;
      }
      setScreen("chat");
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
    const { username: registered, token } = await api.register(name);
    api.setAuthToken(token);
    await storageSet({
      [CONFIG.STORAGE_KEY_USERNAME]: registered,
      [CONFIG.STORAGE_KEY_TOKEN]: token,
    });
    setPendingUsername(registered);
    setObStep("target_lang");
  }

  // Sign out: forget local credentials and restart the onboarding flow,
  // which doubles as the login screen (Google or a fresh profile).
  async function signOut() {
    await storageRemove([CONFIG.STORAGE_KEY_USERNAME, CONFIG.STORAGE_KEY_TOKEN]);
    api.setAuthToken(null);
    setObStep("native_lang");
    setScreen("chat");
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
  async function handleTargetLangSelected(lang: string) {
    setTargetLang(lang);
    setPendingTargetLang(lang);
    setObStep("level_setup");
  }

  // Step 4: level/goals/prompt entered → save settings → enter app
  async function handleLevelSetupComplete(opts: { level: string; goals: string; prompt: string }) {
    try {
      await api.saveSettings(pendingUsername, {
        englishLevel: opts.level,
        goals: opts.goals,
        generalPrompt: opts.prompt,
        nativeLang: pendingNativeLang,
        targetLang: pendingTargetLang,
      });
    } catch { /* ignore — user can update in Settings later */ }
    setLangPair(pendingTargetLang, pendingNativeLang);
    setUsername(pendingUsername);
    setScreen("chat");
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
          <NativeLangScreen onContinue={handleNativeLangSelected} />
        )}
        {obStep === "username" && (
          <OnboardingScreen
            onComplete={handleUsernameEntered}
            onGoogle={isExtension && CONFIG.GOOGLE_CLIENT_ID ? handleGoogleSignIn : undefined}
          />
        )}
        {obStep === "target_lang" && (
          <TargetLangScreen
            nativeLang={pendingNativeLang}
            onContinue={handleTargetLangSelected}
          />
        )}
        {obStep === "level_setup" && (
          <LevelSetupScreen onComplete={handleLevelSetupComplete} />
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
  };

  const pageMeta: Record<string, { title: string; sub: string }> = {
    chat: { title: t.nav_assistant, sub: t.sub_assistant },
    topics: { title: t.nav_topics, sub: t.sub_topics },
    statistics: { title: t.nav_stats, sub: t.sub_stats },
    settings: { title: t.nav_settings, sub: t.sub_settings },
    debug: { title: t.debug_title, sub: "" },
  };
  const meta = pageMeta[screen] ?? pageMeta.chat;

  const navItem = (
    key: string,
    label: string,
    icon: React.ReactNode,
    onClick: () => void,
    active: boolean,
  ) => (
    <button className={`shell-nav-item${active ? " active" : ""}`} onClick={onClick} key={key}>
      {icon}
      {label}
    </button>
  );

  return (
    <AppContext.Provider value={ctx}>
      <div className="app" onClick={handleAppClick}>
        <aside className="shell-sidebar">
          <div className="shell-brand">
            <div className="shell-brand-mark">VE</div>
            <div className="shell-brand-name">Veksha</div>
          </div>
          <nav className="shell-nav">
            {navItem("chat", t.nav_assistant, NavIcons.assistant, () => navigateTo("chat"), screen === "chat")}
            {navItem("topics", t.nav_topics, NavIcons.topics, () => navigateTo("topics"), screen === "topics")}
            {navItem("training", t.nav_training, NavIcons.training, openTraining, false)}
            {isExtension && <SidebarImmersion username={username} onExplain={() => setImmModal(true)} />}
            {navItem("stats", t.nav_stats, NavIcons.stats, () => navigateTo("statistics"), screen === "statistics")}
            <div className="shell-nav-sep" />
            {navItem("settings", t.nav_settings, NavIcons.settings, () => navigateTo("settings", { settingsMode: "menu" }), screen === "settings")}
            {navItem("debug", t.debug_title, NavIcons.settings, () => navigateTo("debug"), screen === "debug")}
          </nav>
          <SidebarWordCount username={username} />
        </aside>

        <div className="shell-main">
          <div className="shell-topbar">
            <div>
              <div className="shell-page-title">{meta.title}</div>
              {meta.sub && <div className="shell-page-sub">{meta.sub}</div>}
            </div>
            <div className="shell-topbar-spacer" />
            <button className="shell-btn-primary" onClick={openTraining}>{t.topbar_train}</button>
          </div>

          <div className="shell-content">
            {screen === "chat" && <ChatScreen />}
            {screen === "topics" && <TopicsScreen />}
            {screen === "settings" && <SettingsScreen />}
            {screen === "statistics" && <StatisticsScreen />}
            {screen === "debug" && <DebugScreen />}
          </div>
        </div>

        {showTour && <TourScreen onFinish={() => setShowTour(false)} />}

        {immModal && (
          <div className="imm-modal-backdrop" onClick={() => setImmModal(false)}>
            <div className="imm-modal" onClick={(e) => e.stopPropagation()}>
              <div className="imm-modal-icon">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 3l1.7 4.8 4.8 1.7-4.8 1.7L12 16l-1.7-4.8-4.8-1.7 4.8-1.7z" />
                  <path d="M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
                </svg>
              </div>
              <h3>{t.imm_modal_title}</h3>
              <p className="imm-modal-sub">{t.imm_modal_sub}</p>
              <div className="imm-card pink">
                <div className="imm-card-ic">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 8V6a2 2 0 0 1 2-2h2" /><path d="M16 4h2a2 2 0 0 1 2 2v2" />
                    <path d="M20 16v2a2 2 0 0 1-2 2h-2" /><path d="M8 20H6a2 2 0 0 1-2-2v-2" />
                    <path d="M8 12h8" />
                  </svg>
                </div>
                <div className="imm-card-body">
                  <div className="imm-card-title">{t.imm_card1_title}</div>
                  <div className="imm-card-desc">{t.imm_card1_desc}</div>
                </div>
              </div>
              <div className="imm-card blue">
                <div className="imm-card-ic">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18h6" /><path d="M10 21h4" />
                    <path d="M12 3a6 6 0 0 0-4 10.4c.6.6 1 1.4 1 2.2v.4h6v-.4c0-.8.4-1.6 1-2.2A6 6 0 0 0 12 3z" />
                  </svg>
                </div>
                <div className="imm-card-body">
                  <div className="imm-card-title">{t.imm_card2_title}</div>
                  <div className="imm-card-desc">{t.imm_card2_desc}</div>
                </div>
              </div>
              <div className="imm-card pink">
                <div className="imm-card-ic">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 20h5v-5h5v-5h5V5h3" />
                  </svg>
                </div>
                <div className="imm-card-body">
                  <div className="imm-card-title">
                    {t.imm_card3_title}
                    <span className="imm-badge">i + 1</span>
                  </div>
                  <div className="imm-card-desc">{t.imm_card3_desc}</div>
                </div>
              </div>
              <div className="imm-modal-actions">
                <button className="btn btn-gradient imm-ok-btn" onClick={() => setImmModal(false)}>
                  {t.imm_modal_ok}
                </button>
                <button
                  className="imm-known-btn"
                  onClick={() => { storageSet({ [immersionExplainedKey(username)]: true }); setImmModal(false); }}
                >
                  {t.imm_modal_known}
                </button>
              </div>
            </div>
          </div>
        )}

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
