import { useEffect, useRef, useState } from "react";
import * as api from "../../shared/api";
import { GoogleMark } from "../../shared/GoogleMark";
import { useI18n, useT } from "../../shared/i18n";
import { CONFIG } from "../../shared/config";
import { googleLinkAccount } from "../../shared/googleAuth";
import { LANGUAGES } from "../../shared/languages"; 
import { isExtension, storageGet, storageRemove, storageSet } from "../../shared/platform";
import { THEMES, type ThemeName, getTheme, previewTheme, setTheme } from "../../shared/theme";
import { useApp } from "../App";
import { normalizeAiBlocklist, siteKey, type AiBlocklist } from "../../shared/aiBlocklist";
import { normalizeFocusSite, type FocusMode, type FocusSession } from "../../shared/focusSession";

// Written by the background when a Google-link flow finishes after the popup 
// has already closed (the OAuth window steals focus and kills the popup).
const GOOGLE_LINK_RESULT_KEY = "vk_google_link_result";

type GoogleLinkResult = { ok: boolean; email?: string; error?: string };

const LANG_OPTIONS = LANGUAGES.filter((l) => l.code !== "auto");
 
function detectNativeLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANG_OPTIONS.some((l) => l.code === raw) ? raw : "en";
}

export function SettingsScreen() {
  const { username, settingsMode, navigateTo, openSubscription, setLangPair, signOut, targetLang: appTargetLang, nativeLang: appNativeLang } = useApp(); 
  const { switchLanguage } = useI18n();
  const t = useT();

  const [displayName, setDisplayName] = useState("");
  const [theme, setThemeState] = useState<ThemeName>("light");
  const [account, setAccount] = useState<api.AccountData | null>(null);
  const [linking, setLinking] = useState(false); 
  const [linkError, setLinkError] = useState<string | null>(null);
  const [billing, setBilling] = useState<api.BillingStatus | null>(null);
  const [promoCode, setPromoCode] = useState("");
  const [promoSubmitting, setPromoSubmitting] = useState(false);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoSuccess, setPromoSuccess] = useState(false);
  const [cancellingSubscription, setCancellingSubscription] = useState(false); 
  const [level, setLevel] = useState("");
  const [goals, setGoals] = useState("");
  const [prompt, setPrompt] = useState("");
  const [nativeLang, setNativeLang] = useState(() => appNativeLang || detectNativeLang());
  const [targetLang, setTargetLang] = useState(() => appTargetLang || "en");
  const [targetLangs, setTargetLangs] = useState<string[]>(() => [appTargetLang || "en"]);
  const [languageSettings, setLanguageSettings] = useState<Record<string, { level: string; goals: string; prompt: string }>>({}); 
  const [reminderLevel, setReminderLevel] = useState(2);
  const [miningSameLevelExamples, setMiningSameLevelExamples] = useState(2);
  const [miningHigherLevelExamples, setMiningHigherLevelExamples] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [settingsLoaded, setSettingsLoaded] = useState(false); 
  const [aiBlocklist, setAiBlocklist] = useState<AiBlocklist>({ sites: [], pages: [], allowedPages: [] });
  const [blockedSiteInput, setBlockedSiteInput] = useState("");
  const [blockedSiteError, setBlockedSiteError] = useState(false);
  const [focusSession, setFocusSession] = useState<FocusSession | null>(null);
  const [focusIntention, setFocusIntention] = useState("");
  const [focusDuration, setFocusDuration] = useState(40);
  const [focusMode, setFocusMode] = useState<FocusMode>("soft"); 
  const [focusSites, setFocusSites] = useState<string[]>([]);
  const [focusSiteInput, setFocusSiteInput] = useState("");
  const savedThemeRef = useRef<ThemeName | null>(null);
  const themeSavedRef = useRef(false);
  const themeTouchedRef = useRef(false);

  const isOnboarding = settingsMode === "onboarding"; 
  const canLinkGoogle = Boolean(CONFIG.GOOGLE_CLIENT_ID);
  const themeLabels: Record<ThemeName, string> = {
    light: t.theme_light,
    grove: t.theme_grove,
    dark: t.theme_dark,
  };
 
  useEffect(() => {
    if (!isExtension || isOnboarding) return;
    storageGet([CONFIG.STORAGE_KEY_AI_BLOCKLIST]).then((result) => {
      setAiBlocklist(normalizeAiBlocklist(result[CONFIG.STORAGE_KEY_AI_BLOCKLIST]));
    }).catch(() => {});
  }, [isOnboarding]);
 
  useEffect(() => {
    if (!isExtension || isOnboarding) return;
    storageGet([CONFIG.STORAGE_KEY_FOCUS_SESSION]).then((values) => {
      const stored = values[CONFIG.STORAGE_KEY_FOCUS_SESSION] as FocusSession | undefined;
      if (stored && stored.endsAt > Date.now()) {
        setFocusSession(stored);
        setFocusSites(stored.sites); 
        setFocusIntention(stored.intention);
        setFocusMode(stored.mode);
      }
    }).catch(() => {});
  }, [isOnboarding]);

  function addFocusSite() { 
    const site = normalizeFocusSite(focusSiteInput);
    if (!site) return;
    setFocusSites((current) => [...new Set([...current, site])]);
    setFocusSiteInput("");
  }

  async function startFocusSession() { 
    if (!focusIntention.trim() || !focusSites.length) return;
    const now = Date.now();
    const next: FocusSession = {
      sessionId: crypto.randomUUID(),
      intention: focusIntention.trim(),
      startedAt: now,
      endsAt: now + focusDuration * 60 * 1000, 
      sites: focusSites,
      mode: focusMode,
      graceUntil: {},
    };
    await storageSet({ [CONFIG.STORAGE_KEY_FOCUS_SESSION]: next });
    setFocusSession(next);
  } 

  async function endFocusSession() {
    await storageRemove([CONFIG.STORAGE_KEY_FOCUS_SESSION]);
    setFocusSession(null);
  }

  function saveAiBlocklist(next: AiBlocklist) { 
    setAiBlocklist(next);
    void storageSet({ [CONFIG.STORAGE_KEY_AI_BLOCKLIST]: next });
  }

  function addBlockedSite() {
    const site = siteKey(blockedSiteInput.trim());
    if (!site) { setBlockedSiteError(true); return; } 
    saveAiBlocklist({ ...aiBlocklist, sites: [...new Set([...aiBlocklist.sites, site])] });
    setBlockedSiteInput("");
    setBlockedSiteError(false);
  }

  function removeBlockedEntry(kind: "site" | "page", value: string) {
    saveAiBlocklist(kind === "site" 
      ? {
          ...aiBlocklist,
          sites: aiBlocklist.sites.filter((item) => item !== value),
          allowedPages: aiBlocklist.allowedPages.filter((page) => siteKey(page) !== value),
        }
      : { ...aiBlocklist, pages: aiBlocklist.pages.filter((item) => item !== value) });
  } 

  useEffect(() => {
    let alive = true;
    getTheme().then((savedTheme) => {
      if (!alive) return;
      savedThemeRef.current = savedTheme;
      if (!themeTouchedRef.current) setThemeState(savedTheme); 
    });
    return () => {
      alive = false;
      if (themeSavedRef.current) return;
      if (savedThemeRef.current) previewTheme(savedThemeRef.current);
      else void getTheme().then(previewTheme);
    }; 
  }, []);

  function pickTheme(name: ThemeName) {
    themeTouchedRef.current = true;
    setThemeState(name);
    previewTheme(name);
  } 

  useEffect(() => {
    if (isOnboarding) return;
    api.getAccount().then(setAccount).catch(() => {});
    api.getBillingStatus().then(setBilling).catch(() => {});
    // Show the outcome of a link flow that finished after the popup closed.
    storageGet([GOOGLE_LINK_RESULT_KEY]).then((res) => { 
      const r = res[GOOGLE_LINK_RESULT_KEY] as GoogleLinkResult | undefined;
      if (!r) return;
      storageRemove([GOOGLE_LINK_RESULT_KEY]);
      applyLinkResult(r);
    }).catch(() => {});
  }, [username, isOnboarding]);
 
  function applyLinkResult(r: GoogleLinkResult) {
    if (r.ok) {
      setLinkError(null);
      setAccount((a) => (a ? { ...a, google_linked: true, google_email: r.email ?? "" } : a));
    } else if (r.error !== "cancelled") {
      setLinkError(r.error === "taken" ? t.settings_google_link_taken : t.onboarding_google_err);
    } 
  }

  async function handleLinkGoogle() {
    setLinking(true);
    setLinkError(null);
    try {
      if (!isExtension) { 
        const result = await googleLinkAccount();
        applyLinkResult({ ok: result.ok, email: result.email });
        return;
      }
      // The flow runs in the background — it survives this popup closing.
      const r = (await chrome.runtime.sendMessage({ type: "VEKSHA_GOOGLE_LINK" })) as
        | GoogleLinkResult 
        | undefined;
      if (r) {
        applyLinkResult(r);
        await storageRemove([GOOGLE_LINK_RESULT_KEY]);
      }
    } catch {
      // Popup survived but messaging failed — the persisted result (if any) 
      // will be shown on the next open.
    } finally {
      setLinking(false);
    }
  }

  async function handleRedeemPromo() { 
    const code = promoCode.trim();
    if (!code || promoSubmitting) return;
    setPromoSubmitting(true);
    setPromoError(null);
    setPromoSuccess(false);
    try {
      const result = await api.redeemPromoCode(code); 
      if (result.ok) {
        setPromoCode("");
        setPromoSuccess(true);
        setBilling(await api.getBillingStatus());
      } else {
        setPromoError(
          result.error === "exhausted" ? t.settings_promo_error_exhausted 
          : result.error === "already_redeemed" ? t.settings_promo_error_already_redeemed
          : t.settings_promo_error_invalid,
        );
      }
    } catch {
      setPromoError(t.settings_promo_error_generic);
    } finally { 
      setPromoSubmitting(false);
    }
  }

  async function handleCancelSubscription() {
    if (!confirm(t.subscription_cancel_confirm)) return;
    setCancellingSubscription(true); 
    try {
      setBilling(await api.cancelSubscription());
    } catch {
      setError(t.subscription_cancel_error);
    } finally {
      setCancellingSubscription(false);
    } 
  }

  async function handleSignOut() {
    // Without a Google link the profile becomes unreachable after sign-out.
    if (!account?.google_linked && !confirm(t.settings_signout_confirm)) return;
    await signOut();
  } 

  // CEFR grade scale (labels are universal codes — no translation needed).
  const ENGLISH_LEVELS = [
    { value: "a1", label: "A1" },
    { value: "a1_a2", label: "A1/A2" },
    { value: "a2", label: "A2" },
    { value: "a2_b1", label: "A2/B1" }, 
    { value: "b1", label: "B1" },
    { value: "b1_b2", label: "B1/B2" },
    { value: "b2", label: "B2" },
    { value: "b2_c1", label: "B2/C1" },
    { value: "c1", label: "C1" },
    { value: "c1_c2", label: "C1/C2" },
    { value: "c2", label: "C2" }, 
  ];

  useEffect(() => {
    let alive = true;
    setLoadingSettings(true);
    setSettingsLoaded(false);
    setError(null); 
    api.getSettings(username).then((s) => {
      if (!alive) return;
      setDisplayName(s.display_name ?? "");
      setLevel(s.english_level ?? "");
      setGoals(s.goals);
      setPrompt(s.general_prompt);
      setNativeLang(s.native_lang || detectNativeLang()); 
      setTargetLang(s.target_lang || "en");
      setTargetLangs(s.target_langs?.length ? s.target_langs : [s.target_lang || "en"]);
      setLanguageSettings(s.language_settings ?? {});
      setReminderLevel(s.reminder_level ?? 2);
      setMiningSameLevelExamples(s.mining_same_level_examples ?? 2);
      setMiningHigherLevelExamples(s.mining_higher_level_examples ?? 1);
      setSettingsLoaded(true); 
    }).catch((err) => {
      if (!alive) return;
      setNativeLang(appNativeLang || detectNativeLang());
      setTargetLang(appTargetLang || "en");
      setError(`${t.settings_err_load}: ${(err as Error).message}`);
    }).finally(() => {
      if (alive) setLoadingSettings(false); 
    });
    return () => { alive = false; };
  }, [username, appNativeLang, appTargetLang, t.settings_err_load]);

  async function handleSave() {
    if (loadingSettings || !settingsLoaded) return;
    if (!level) { setError(t.settings_err_no_level); return; } 
    if (nativeLang === targetLang) { setError(t.settings_err_same_lang); return; }
    setError(null);
    setSaving(true);
    try {
      const updatedLanguageSettings = {
        ...languageSettings,
        [targetLang]: { level, goals, prompt }, 
      };
      await api.saveSettings(username, {
        displayName,
        englishLevel: level,
        goals,
        generalPrompt: prompt,
        nativeLang, 
        targetLang,
        targetLangs,
        languageSettings: updatedLanguageSettings,
        reminderLevel,
        miningSameLevelExamples,
        miningHigherLevelExamples,
      }); 

      const localSettings: Record<string, unknown> = {
        [CONFIG.STORAGE_KEY_NATIVE_LANG]: nativeLang,
      };
      await storageSet(localSettings);
      await setTheme(theme);
      savedThemeRef.current = theme; 
      themeSavedRef.current = true;
      previewTheme(theme);

      setLangPair(targetLang, nativeLang);
      await switchLanguage(nativeLang);
      navigateTo("home");
    } catch (err) { 
      setError(`${t.settings_err_save}: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  function handleTargetLangChange(nextLang: string) { 
    const updated = {
      ...languageSettings,
      [targetLang]: { level, goals, prompt },
    };
    const next = updated[nextLang] ?? { level: "", goals: "", prompt: "" };
    setLanguageSettings(updated);
    setTargetLang(nextLang); 
    setLevel(next.level);
    setGoals(next.goals);
    setPrompt(next.prompt);
  }

  function handleAddTargetLang(nextLang: string) {
    if (!nextLang || nextLang === nativeLang || targetLangs.includes(nextLang)) return; 
    const updated = {
      ...languageSettings,
      [targetLang]: { level, goals, prompt },
      [nextLang]: { level: "", goals: "", prompt: "" },
    };
    setLanguageSettings(updated);
    setTargetLangs((current) => [...current, nextLang]); 
    setTargetLang(nextLang);
    setLevel("");
    setGoals("");
    setPrompt("");
    setError(null);
  }
 
  function handleRemoveTargetLang(lang: string) {
    if (targetLangs.length <= 1) return;

    const remaining = targetLangs.filter((code) => code !== lang);
    const updated = {
      ...languageSettings,
      [targetLang]: { level, goals, prompt }, 
    };
    delete updated[lang];
    setTargetLangs(remaining);
    setLanguageSettings(updated);

    if (lang === targetLang) {
      const nextLang = remaining[0]; 
      const next = updated[nextLang] ?? { level: "", goals: "", prompt: "" };
      setTargetLang(nextLang);
      setLevel(next.level);
      setGoals(next.goals);
      setPrompt(next.prompt);
    }
    setError(null); 
  }

  function btnLabel() {
    if (saving) return t.settings_saving;
    return t.settings_save;
  } 

  return (
    <section className="screen screen-settings">
      <header className="menu-header">
        <span className="menu-title">{t.settings_title}</span>
        {!isOnboarding && (
          <button className="icon-btn" aria-label="Close" style={{ marginLeft: "auto" }} onClick={() => navigateTo("home")}> 
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        )}
      </header>
 
      <div className="settings-body">
        {loadingSettings && (
          <p className="settings-intro">{t.app_loading}</p>
        )}

        {isOnboarding && (
          <p className="settings-intro">{t.settings_intro}</p> 
        )}

        {!isOnboarding && (
          <>
            <label className="field-label">{t.settings_theme}</label>
            <div className="theme-swatches">
              {THEMES.map((name) => ( 
                <button
                  key={name}
                  type="button"
                  className={`theme-swatch theme-swatch-${name}${theme === name ? " is-active" : ""}`}
                  title={themeLabels[name]}
                  aria-label={themeLabels[name]}
                  onClick={() => pickTheme(name)} 
                />
              ))}
            </div>
          </>
        )}

        <label className="field-label" htmlFor="settings-display-name">{t.settings_display_name}</label> 
        <input
          id="settings-display-name"
          className="text-input"
          type="text"
          maxLength={64}
          placeholder={t.onboarding_name_placeholder}
          value={displayName} 
          onChange={(e) => setDisplayName(e.target.value)}
        />

        <label className="field-label" htmlFor="settings-native-lang">{t.settings_native_lang}</label>
        <select
          id="settings-native-lang"
          className="select-input" 
          value={nativeLang}
          onChange={(e) => setNativeLang(e.target.value)}
        >
          {LANG_OPTIONS.filter((l) => l.code === nativeLang || !targetLangs.includes(l.code)).map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select> 

        {!isOnboarding && (
          <>
            <label className="field-label">{t.settings_learning_languages}</label>
            <div className="settings-language-list">
              {targetLangs.map((code) => {
                const language = LANG_OPTIONS.find((item) => item.code === code); 
                return (
                  <div className={`settings-language-item${code === targetLang ? " is-active" : ""}`} key={code}>
                    <button type="button" className="settings-language-select" onClick={() => handleTargetLangChange(code)}>
                      <span className="settings-language-code">{code.toUpperCase()}</span>
                      <span>{language?.name ?? code}</span>
                    </button>
                    <button 
                      type="button"
                      className="settings-language-remove"
                      aria-label={`${t.settings_remove_language}: ${language?.name ?? code}`}
                      title={t.settings_remove_language}
                      disabled={targetLangs.length <= 1}
                      onClick={() => handleRemoveTargetLang(code)}
                    > 
                      <span aria-hidden="true">×</span>
                    </button>
                  </div>
                );
              })}
            </div>
            <select 
              className="select-input settings-language-add"
              value=""
              aria-label={t.settings_add_language}
              onChange={(e) => handleAddTargetLang(e.target.value)}
            >
              <option value="">＋ {t.settings_add_language}</option>
              {LANG_OPTIONS.filter((l) => l.code !== nativeLang && !targetLangs.includes(l.code)).map((l) => ( 
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </select>
          </>
        )}

        <label className="field-label" htmlFor="settings-target-lang">{t.settings_target_lang}</label> 
        <select
          id="settings-target-lang"
          className="select-input"
          value={targetLang}
          onChange={(e) => handleTargetLangChange(e.target.value)}
        >
          {LANG_OPTIONS.filter((l) => targetLangs.includes(l.code)).map((l) => ( 
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>

        <label className="field-label" htmlFor="settings-level">{t.settings_level}</label>
        <select
          id="settings-level" 
          className="select-input"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option value="" disabled>{t.settings_level_placeholder}</option>
          {ENGLISH_LEVELS.map((l) => (
            <option key={l.value} value={l.value}>{l.label}</option> 
          ))}
        </select>

        <label className="field-label" htmlFor="settings-goals">{t.settings_goals}</label>
        <textarea
          id="settings-goals"
          className="textarea-input" 
          rows={3}
          placeholder={t.settings_goals_placeholder}
          value={goals}
          onChange={(e) => setGoals(e.target.value)}
        />

        <label className="field-label" htmlFor="settings-prompt">{t.settings_prompt_label}</label> 
        <textarea
          id="settings-prompt"
          className="textarea-input"
          rows={3}
          placeholder={t.settings_prompt_placeholder}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)} 
        />

        {!isOnboarding && (
          <div className="settings-mining">
            <span className="settings-toggle-title">{t.settings_mining_title}</span>
            <span className="settings-toggle-desc">{t.settings_mining_desc}</span>
            <label> 
              <span>{t.settings_mining_current}</span>
              <select
                className="select-input"
                value={miningSameLevelExamples}
                onChange={(event) => setMiningSameLevelExamples(Number(event.target.value))}
              >
                {[1, 2, 3, 4, 5].map((count) => <option key={count} value={count}>{count}</option>)} 
              </select>
            </label>
            <label>
              <span>{t.settings_mining_higher}</span>
              <select
                className="select-input"
                value={miningHigherLevelExamples} 
                onChange={(event) => setMiningHigherLevelExamples(Number(event.target.value))}
              >
                {[0, 1, 2, 3].map((count) => <option key={count} value={count}>{count}</option>)}
              </select>
            </label>
          </div>
        )} 

        <div className="settings-level">
          <span className="settings-toggle-title">{t.settings_reminder_level}</span>
          <span className="settings-toggle-desc">{t.settings_reminder_level_desc}</span>
          <input
            type="range"
            className="settings-level-range" 
            min={1}
            max={3}
            step={1}
            value={reminderLevel}
            onChange={(e) => setReminderLevel(Number(e.target.value))}
          />
          <div className="settings-level-ticks"> 
            <button
              type="button"
              className={reminderLevel === 1 ? "is-active" : ""}
              onClick={() => setReminderLevel(1)}
            >
              {t.settings_reminder_level_1}
            </button> 
            <button
              type="button"
              className={reminderLevel === 2 ? "is-active" : ""}
              onClick={() => setReminderLevel(2)}
            >
              {t.settings_reminder_level_2}
            </button> 
            <button
              type="button"
              className={reminderLevel === 3 ? "is-active" : ""}
              onClick={() => setReminderLevel(3)}
            >
              {t.settings_reminder_level_3}
            </button> 
          </div>
        </div>

        {error && <p className="onboarding-error">{error}</p>}

        {!isOnboarding && (
          <section className="settings-panel settings-focus-session"> 
            <div className="settings-panel-heading">
              <span className="settings-panel-icon" aria-hidden="true">◷</span>
              <div>
                <h2>{t.focus_session_title}</h2>
                <p>{t.focus_session_desc}</p>
              </div>
            </div> 
            {focusSession ? (
              <div className="focus-session-active">
                <strong>{focusSession.intention}</strong>
                <span>{t.focus_session_active.replace("{n}", String(Math.max(1, Math.ceil((focusSession.endsAt - Date.now()) / 60000))))}</span>
                <button className="btn btn-ghost" type="button" onClick={() => void endFocusSession()}>{t.focus_session_end}</button>
              </div>
            ) : ( 
              <div className="focus-session-form">
                <label>{t.focus_session_intention}<input value={focusIntention} onChange={(event) => setFocusIntention(event.target.value)} placeholder={t.focus_session_intention_placeholder} /></label>
                <div className="focus-session-durations">
                  {[20, 40, 60].map((minutes) => <button type="button" className={focusDuration === minutes ? "is-active" : ""} onClick={() => setFocusDuration(minutes)} key={minutes}>{minutes} min</button>)}
                </div>
                <div className="settings-blocklist-add">
                  <input value={focusSiteInput} onChange={(event) => setFocusSiteInput(event.target.value)} placeholder={t.focus_session_site_placeholder} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addFocusSite(); } }} /> 
                  <button className="btn settings-blocklist-add-btn" type="button" onClick={addFocusSite}>{t.ai_block_add}</button>
                </div>
                <div className="settings-blocklist-items">
                  {focusSites.map((site) => <div className="settings-blocklist-item" key={site}><span>{site}</span><button type="button" onClick={() => setFocusSites((items) => items.filter((item) => item !== site))}>×</button></div>)}
                </div>
                <label className="focus-session-mode"><input type="checkbox" checked={focusMode === "strict"} onChange={(event) => setFocusMode(event.target.checked ? "strict" : "soft")} />{t.focus_session_strict}</label>
                <button className="btn btn-gradient btn-block" type="button" disabled={!focusIntention.trim() || !focusSites.length} onClick={() => void startFocusSession()}>{t.focus_session_start}</button> 
              </div>
            )}
          </section>
        )}

        {!isOnboarding && (
          <section className="settings-panel settings-blocklist"> 
            <div className="settings-panel-heading">
              <span className="settings-panel-icon" aria-hidden="true">⊘</span>
              <div>
                <h2>{t.ai_block_settings_title}</h2>
                <p>{t.ai_block_settings_desc}</p>
              </div>
            </div> 
            <div className="settings-blocklist-add">
              <input
                className="text-input"
                type="text"
                value={blockedSiteInput}
                placeholder={t.ai_block_add_placeholder}
                onChange={(event) => { setBlockedSiteInput(event.target.value); setBlockedSiteError(false); }} 
                onKeyDown={(event) => { if (event.key === "Enter") addBlockedSite(); }}
              />
              <button className="btn settings-blocklist-add-btn" type="button" onClick={addBlockedSite} disabled={!blockedSiteInput.trim()}>{t.ai_block_add}</button>
            </div>
            {blockedSiteError && <p className="onboarding-error">{t.ai_block_invalid}</p>}
            <div className="settings-blocklist-items">
              {aiBlocklist.sites.map((site) => ( 
                <div className="settings-blocklist-item" key={`site:${site}`}>
                  <span><b>{site}</b><small>{t.ai_block_disable_site}</small></span>
                  <button type="button" onClick={() => removeBlockedEntry("site", site)}>{t.ai_block_remove}</button>
                </div>
              ))}
              {aiBlocklist.pages.map((page) => (
                <div className="settings-blocklist-item" key={`page:${page}`}> 
                  <span><b>{page}</b><small>{t.ai_block_disable_page}</small></span>
                  <button type="button" onClick={() => removeBlockedEntry("page", page)}>{t.ai_block_remove}</button>
                </div>
              ))}
              {!aiBlocklist.sites.length && !aiBlocklist.pages.length && <p className="settings-blocklist-empty">{t.ai_block_empty}</p>}
            </div>
          </section> 
        )}

        {!isOnboarding && (
          <div className="settings-account">
            <label className="field-label">{t.settings_subscription}</label>
            <p className="settings-account-status">
              {billing?.tier === "premium" 
                ? billing.expires_at
                  ? `⭐ ${t.settings_sub_premium} ${new Date(billing.expires_at * 1000).toLocaleDateString()}`
                  : `⭐ ${t.settings_sub_premium_active}`
                : t.settings_sub_free}
            </p>
            {billing?.tier !== "premium" && (
              <span className="settings-toggle-desc">{t.settings_sub_desc}</span> 
            )}
            <button
              className="btn"
              type="button"
              onClick={() => openSubscription({ mode: billing?.tier === "premium" ? "manage" : "new" })}
            >
              {billing?.tier === "premium" ? t.settings_sub_manage : t.settings_sub_connect} 
            </button>
            {billing?.tier === "premium" && (
              <button
                className="btn btn-signout"
                type="button"
                disabled={cancellingSubscription}
                onClick={handleCancelSubscription} 
              >
                {cancellingSubscription ? t.app_loading : t.subscription_cancel}
              </button>
            )}
            <label className="field-label" htmlFor="settings-promo-code">{t.settings_promo_label}</label>
            <div className="settings-promo-row">
              <input 
                id="settings-promo-code"
                className="text-input"
                type="text"
                maxLength={64}
                placeholder={t.settings_promo_placeholder}
                value={promoCode}
                onChange={(e) => { 
                  setPromoCode(e.target.value);
                  setPromoError(null);
                  setPromoSuccess(false);
                }}
                onKeyDown={(e) => { if (e.key === "Enter") handleRedeemPromo(); }}
              />
              <button 
                className="btn"
                disabled={promoSubmitting || !promoCode.trim()}
                onClick={handleRedeemPromo}
              >
                {t.settings_promo_submit}
              </button>
            </div> 
            {promoError && <p className="onboarding-error">{promoError}</p>}
            {promoSuccess && <p className="settings-toggle-desc">{t.settings_promo_success}</p>}
          </div>
        )}

        {!isOnboarding && (
          <div className="settings-account"> 
            <label className="field-label">{t.settings_account}</label>
            {account?.google_linked ? (
              <p className="settings-account-status">
                <GoogleMark />
                {t.settings_google_linked}
                {account.google_email ? ` · ${account.google_email}` : ""}
              </p> 
            ) : canLinkGoogle ? (
              <button className="btn btn-google" disabled={linking} onClick={handleLinkGoogle}>
                <GoogleMark />
                {t.settings_google_link}
              </button>
            ) : null}
            {linkError && <p className="onboarding-error">{linkError}</p>} 
            <button className="btn btn-signout" onClick={handleSignOut}>
              {t.settings_signout}
            </button>
          </div>
        )}
      </div>
 
      <div className="settings-footer">
        <button className="btn btn-gradient btn-block" disabled={saving || loadingSettings || !settingsLoaded} onClick={handleSave}>
          {btnLabel()}
        </button>
      </div>

    </section> 
  );
}
