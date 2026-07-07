import { CONFIG } from "../shared/config";
import { LANGUAGES } from "../shared/languages";
import { quickTranslate, explain, getSettings } from "../shared/api";
import { canSpeak, speakText } from "../shared/speech";
import { showTrainingOverlay, showLessonOverlay, showTopicPickerOverlay, showTutorialOverlay } from "./overlay";
import { initYouTubeStudy, YT_STUDY_GUARD_SELECTOR } from "./youtube";
import { initImmersion, setImmersionEnabled } from "./immersion";

let icon: HTMLElement | null = null;
let popup: HTMLElement | null = null;
let aggressiveReminder: HTMLElement | null = null;
let terrorEvasionTimer: ReturnType<typeof setInterval> | null = null;
let terrorCaptionTimer: ReturnType<typeof setInterval> | null = null;
let terrorPointerHandler: ((event: PointerEvent) => void) | null = null;
let terrorEvasion = 86;
let lastSelectionText = "";
let cachedUsername: string | null = null;
let translationRequestId = 0;

// Last cursor position — used to anchor the popup for the right-click
// "Translate selection" flow (the context menu gives no coordinates).
let lastMouse = { x: 40, y: 120 };
document.addEventListener("mousemove", (e) => { lastMouse = { x: e.clientX, y: e.clientY }; }, { capture: true, passive: true });
// The exact right-click point — used to anchor the "Translate selection" popup
// (the context menu itself gives no coordinates).
document.addEventListener("contextmenu", (e) => { lastMouse = { x: e.clientX, y: e.clientY }; }, { capture: true });

// ---------------------------------------------------------------------------
// i18n — loaded from chrome.storage.local (key: av_i18n_{lang})
// ---------------------------------------------------------------------------

let i18nStrings: Record<string, string> = {};

function t(key: string, fallback: string): string {
  return (i18nStrings[key] as string | undefined) ?? fallback;
}

async function loadI18n(lang: string): Promise<void> {
  if (!lang || lang === "en") { i18nStrings = {}; return; }
  try {
    const stored = await chrome.storage.local.get([`vk_i18n_${lang}`]);
    i18nStrings = (stored[`vk_i18n_${lang}`] as Record<string, string> | undefined) ?? {};
  } catch { i18nStrings = {}; }
}

// ---------------------------------------------------------------------------
// Translation state — target lang loaded from user settings in storage
// ---------------------------------------------------------------------------

let state: { sourceLang: string; targetLang: string } = {
  sourceLang: CONFIG.DEFAULT_SOURCE_LANG,
  targetLang: CONFIG.DEFAULT_TARGET_LANG,
};

// Bidirectional translation: foreign text → native (to understand); but if the
// selected text is already the user's NATIVE language, translate it INTO the
// language they're studying (to practise producing it).
let nativeLang: string = CONFIG.DEFAULT_TARGET_LANG;
let studiedLang = "";

async function loadLangPair(): Promise<void> {
  try {
    const username = await getUsername();
    if (!username) return;
    const s = await getSettings(username);
    if (s.native_lang) nativeLang = s.native_lang;
    if (s.target_lang) studiedLang = s.target_lang;
  } catch { /* keep defaults */ }
}

function detectBrowserLang(): string {
  return (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
}

// On load: read saved native_lang and i18n cache from storage
chrome.storage.local.get(
  [CONFIG.STORAGE_KEY_NATIVE_LANG],
  (result) => {
    const lang = (result[CONFIG.STORAGE_KEY_NATIVE_LANG] as string | undefined) ?? detectBrowserLang();
    state.targetLang = lang;
    nativeLang = lang;
    loadI18n(lang);
    void loadLangPair();
  }
);

// Keep in sync when user changes settings in the popup
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[CONFIG.STORAGE_KEY_NATIVE_LANG]) {
    const lang = (changes[CONFIG.STORAGE_KEY_NATIVE_LANG].newValue as string | undefined) ?? detectBrowserLang();
    state.targetLang = lang;
    nativeLang = lang;
    loadI18n(lang);
    void loadLangPair();
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function getUsername(): Promise<string | null> {
  if (cachedUsername) return cachedUsername;

  const storageRead = chrome.storage.local.get([CONFIG.STORAGE_KEY_USERNAME]);
  const timeout = new Promise<never>((_, reject) => {
    setTimeout(() => reject(new Error("Extension storage timed out")), 3_000);
  });
  const result = await Promise.race([storageRead, timeout]);
  cachedUsername = (result[CONFIG.STORAGE_KEY_USERNAME] as string) || null;
  return cachedUsername;
}

function removeIcon() { icon?.remove(); icon = null; }
function removePopup() { popup?.remove(); popup = null; }
function removeAll() { removeIcon(); removePopup(); }

function removeAggressiveReminder() {
  if (terrorEvasionTimer) clearInterval(terrorEvasionTimer);
  if (terrorCaptionTimer) clearInterval(terrorCaptionTimer);
  if (terrorPointerHandler) window.removeEventListener("pointermove", terrorPointerHandler, true);
  terrorEvasionTimer = null;
  terrorCaptionTimer = null;
  terrorPointerHandler = null;
  aggressiveReminder?.remove();
  aggressiveReminder = null;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function wordsFromMessage(msg: Record<string, unknown>): string[] {
  const raw = Array.isArray(msg.due_word_names) ? msg.due_word_names : [];
  return raw.map((word) => String(word).trim()).filter(Boolean).slice(0, 8);
}

function buildTerrorLines(words: string[], dueTopic: string | null): string[] {
  const pool = words.length ? words : [dueTopic || "one tiny useful word"];
  const pick = () => pool[Math.floor(Math.random() * pool.length)] || pool[0];
  return [
    `Ты мог бы уже знать "${pick()}". Прямо сейчас.`,
    `Представь, что "${pick()}" уже не бесит, а спокойно живёт в голове.`,
    "Каждую минуту без тренировки ты упускаешь новые слова.",
    "Одна тренировка сейчас дешевле, чем торг с совестью вечером.",
    "Крестик тренирует ловкость. Кнопка тренировки тренирует английский.",
    `Ты уже встречал "${pick()}". Будь вежлив, повтори.`,
    dueTopic ? `Незаконченная тема "${dueTopic}" ждёт с подозрительным терпением.` : "Одна короткая тренировка — и день уже не зря.",
  ];
}

function positionTerrorClose(button: HTMLButtonElement, x?: number, y?: number) {
  const size = 46;
  const nextX = x ?? window.innerWidth - size - 32;
  const nextY = y ?? 32;
  button.style.left = `${clamp(nextX, 14, window.innerWidth - size - 14)}px`;
  button.style.top = `${clamp(nextY, 14, window.innerHeight - size - 14)}px`;
}

function moveTerrorCloseAway(button: HTMLButtonElement, event: PointerEvent) {
  if (terrorEvasion < 20) return;
  const rect = button.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const dx = centerX - event.clientX;
  const dy = centerY - event.clientY;
  const len = Math.hypot(dx, dy) || 1;
  const force = 42 + terrorEvasion * 1.65;
  const wobble = (Math.random() - 0.5) * 76;
  positionTerrorClose(
    button,
    rect.left + (dx / len) * force + wobble,
    rect.top + (dy / len) * force - wobble * 0.35,
  );
}

function updateTerrorMeter(root: HTMLElement, meter: HTMLElement, close: HTMLButtonElement) {
  root.style.setProperty("--terror-evasion", `${terrorEvasion}%`);
  meter.textContent = terrorEvasion < 20
    ? "Ловкость: 18%. Крестик устал, лови."
    : `Ловкость: ${Math.round(terrorEvasion)}%`;
  close.dataset.catchable = terrorEvasion < 20 ? "true" : "false";
}

function showAggressiveReminder(msg: Record<string, unknown>) {
  removeAggressiveReminder();
  terrorEvasion = 86;

  // "Overseer" mode: the close button runs away and the terror game is shown.
  // Without it, level 2/3 still shows the blurred pop-up with a normal close.
  const overseer = Boolean(msg.overseer);

  const dueWords = Number(msg.due_words ?? 0);
  const dueWordNames = wordsFromMessage(msg);
  const dueTopic = typeof msg.due_topic === "string" ? msg.due_topic : null;
  const username = typeof msg.username === "string" ? msg.username : "";
  const parts: string[] = [];
  if (dueWords > 0) parts.push(t("reminder_words", "{n} word(s) to review").replace("{n}", String(dueWords)));
  if (dueTopic) parts.push(`${t("reminder_topic", "unfinished topic")}: "${dueTopic}"`);
  const subtitle = parts.length
    ? t("reminder_have", "You have {items}.").replace("{items}", parts.join(" and "))
    : t("reminder_subtitle_default", "You have words to review.");

  aggressiveReminder = document.createElement("div");
  aggressiveReminder.className = "veksha-aggressive-reminder veksha-terror-reminder";

  const banner = document.createElement("div");
  banner.className = "veksha-aggressive-banner";

  const logo = document.createElement("img");
  logo.className = "veksha-terror-logo";
  logo.src = chrome.runtime.getURL("icons/icon48.png");
  logo.alt = "";

  const copy = document.createElement("div");
  copy.className = "veksha-aggressive-copy";
  const title = document.createElement("div");
  title.className = "veksha-aggressive-title";
  title.textContent = "Время потренироваться!";
  const description = document.createElement("div");
  description.className = "veksha-aggressive-subtitle";
  description.textContent = subtitle;
  copy.append(title, description);

  const start = document.createElement("button");
  start.className = "veksha-aggressive-start";
  start.textContent = t("reminder_start", "Start training");
  start.addEventListener("click", () => {
    removeAggressiveReminder();
    if (username) showTrainingOverlay(username);
  });

  const close = document.createElement("button");
  close.className = overseer
    ? "veksha-aggressive-close veksha-terror-close"
    : "veksha-aggressive-close veksha-static-close";
  close.title = t("reminder_dismiss", "Dismiss reminder");
  close.setAttribute("aria-label", close.title);
  close.textContent = "x";
  if (overseer) {
    close.addEventListener("pointerenter", (event) => moveTerrorCloseAway(close, event));
    close.addEventListener("click", (event) => {
      if (terrorEvasion < 20) {
        removeAggressiveReminder();
        return;
      }
      moveTerrorCloseAway(close, event as PointerEvent);
    });
  } else {
    close.addEventListener("click", () => removeAggressiveReminder());
  }

  banner.append(logo, copy, start);

  let helpPanel: HTMLElement | null = null;
  if (overseer) {
    helpPanel = document.createElement("div");
    helpPanel.className = "veksha-terror-help";
    helpPanel.innerHTML = `
      <div class="veksha-terror-help-title">Как отключить напоминание</div>
      <div class="veksha-terror-help-row">
        <span class="veksha-terror-help-icon">✓</span>
        <span><b>Закончить тренировку</b><small>Самый быстрый способ</small></span>
      </div>
      <div class="veksha-terror-help-row">
        <span class="veksha-terror-help-icon">+</span>
        <span><b>Поймать крестик</b><small>Сложность зависит от ловкости</small></span>
      </div>
      <div class="veksha-terror-help-note">Выбери любой способ, чтобы продолжить.</div>
    `;
  }

  const captions = document.createElement("div");
  captions.className = "veksha-terror-captions";
  const headline = document.createElement("div");
  headline.className = "veksha-terror-headline";
  headline.innerHTML = "Каждую минуту без тренировки<br>ты <span>упускаешь новые слова.</span>";
  const prompt = document.createElement("div");
  prompt.className = "veksha-terror-prompt";
  prompt.textContent = "Представь, что ты уже знаешь:";
  const captionText = document.createElement("div");
  captionText.className = "veksha-terror-caption-text";
  const lines = buildTerrorLines(dueWordNames, dueTopic);
  let captionIndex = 0;
  captionText.textContent = lines[captionIndex];
  const wordStrip = document.createElement("div");
  wordStrip.className = "veksha-terror-word-strip";
  for (const word of dueWordNames.slice(0, 6)) {
    const chip = document.createElement("span");
    chip.textContent = word;
    wordStrip.appendChild(chip);
  }
  captions.append(headline, prompt, captionText);
  if (wordStrip.childElementCount) captions.append(wordStrip);

  const meter = document.createElement("div");
  meter.className = "veksha-terror-meter";

  const squirrel = document.createElement("img");
  squirrel.className = "veksha-aggressive-squirrel";
  squirrel.src = chrome.runtime.getURL("source/squirrel.gif");
  squirrel.alt = "";

  aggressiveReminder.append(banner, captions, squirrel, close);
  if (overseer) {
    if (helpPanel) aggressiveReminder.append(helpPanel);
    aggressiveReminder.append(meter);
  }
  document.documentElement.appendChild(aggressiveReminder);

  terrorCaptionTimer = setInterval(() => {
    captionIndex = (captionIndex + 1) % lines.length;
    captionText.textContent = lines[captionIndex];
  }, 4200);

  if (!overseer) return;

  positionTerrorClose(close);
  updateTerrorMeter(aggressiveReminder, meter, close);

  terrorEvasionTimer = setInterval(() => {
    const step = 10 + Math.random() * 15;
    terrorEvasion = clamp(terrorEvasion + (Math.random() < 0.5 ? -step : step), 0, 100);
    if (aggressiveReminder) updateTerrorMeter(aggressiveReminder, meter, close);
  }, 1000);

  terrorPointerHandler = (event: PointerEvent) => {
    const rect = close.getBoundingClientRect();
    const distance = Math.hypot(event.clientX - (rect.left + rect.width / 2), event.clientY - (rect.top + rect.height / 2));
    if (distance < 140) moveTerrorCloseAway(close, event);
  };
  window.addEventListener("pointermove", terrorPointerHandler, true);
}

function showIcon(rect: DOMRect, selectedText: string) {
  removeIcon();
  icon = document.createElement("div");
  icon.className = "veksha-icon";
  icon.title = "Translate";
  const iconImage = document.createElement("img");
  iconImage.className = "veksha-icon-image";
  iconImage.src = chrome.runtime.getURL("icons/icon48.png");
  iconImage.alt = "";
  icon.appendChild(iconImage);
  const iconSize = 32;
  const gap = 7;
  const fitsRight = rect.right + gap + iconSize <= window.innerWidth;
  icon.style.top = `${window.scrollY + rect.top + Math.max(0, (rect.height - iconSize) / 2)}px`;
  icon.style.left = fitsRight
    ? `${window.scrollX + rect.right + gap}px`
    : `${window.scrollX + Math.max(0, rect.left - gap - iconSize)}px`;
  icon.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); });
  icon.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    openPopup(selectedText, rect);
    removeIcon();
  });
  document.documentElement.appendChild(icon);
}

function buildLanguageOptions(selectEl: HTMLSelectElement, selectedCode: string) {
  selectEl.innerHTML = "";
  for (const lang of LANGUAGES) {
    const opt = document.createElement("option");
    opt.value = lang.code;
    opt.textContent = lang.code === "auto" ? "AUTO" : lang.code.toUpperCase();
    if (lang.code === selectedCode) opt.selected = true;
    selectEl.appendChild(opt);
  }
}

function openPopup(selectedText: string, rect: DOMRect, opts?: { fixed?: boolean }) {
  removePopup();

  // Default direction: translate INTO the native language. The auto-flip below
  // switches to the studied language when the source turns out to be native.
  state.targetLang = nativeLang || state.targetLang;
  let flipped = false;

  popup = document.createElement("div");
  popup.className = "veksha-popup";
  if (opts?.fixed) {
    // PDF viewer (and other overflow:hidden hosts) clip absolutely-positioned
    // children at the page edge — pin to the viewport instead and clamp so the
    // whole popup stays on screen.
    const W = 340, H = 260, gap = 6;
    let left = rect.left;
    left = Math.max(8, Math.min(left, window.innerWidth - W - 8));
    let top = rect.bottom + gap;
    if (top + H > window.innerHeight) top = Math.max(8, rect.top - H - gap);
    popup.style.position = "fixed";
    popup.style.top = `${top}px`;
    popup.style.left = `${left}px`;
  } else {
    popup.style.top = `${window.scrollY + rect.bottom + 6}px`;
    popup.style.left = `${window.scrollX + rect.left}px`;
  }

  // Header
  const header = document.createElement("div");
  header.className = "veksha-header";

  const langRow = document.createElement("div");
  langRow.className = "veksha-lang-row";

  const sourceSelect = document.createElement("select");
  sourceSelect.className = "veksha-select";
  buildLanguageOptions(sourceSelect, state.sourceLang);

  const swapBtn = document.createElement("button");
  swapBtn.className = "veksha-swap";
  swapBtn.title = "Swap languages";
  swapBtn.textContent = "→";

  const targetSelect = document.createElement("select");
  targetSelect.className = "veksha-select";
  buildLanguageOptions(targetSelect, state.targetLang);
  targetSelect.querySelector('option[value="auto"]')?.remove();
  targetSelect.value = state.targetLang;

  langRow.append(sourceSelect, swapBtn, targetSelect);

  const closeBtn = document.createElement("button");
  closeBtn.className = "veksha-close";
  closeBtn.title = "Close";
  closeBtn.textContent = "x";
  closeBtn.addEventListener("click", removeAll);
  header.append(langRow, closeBtn);

  // Result
  const resultBox = document.createElement("div");
  resultBox.className = "veksha-result";
  resultBox.textContent = t("content_translating", "Translating...");

  // Action row
  const actionRow = document.createElement("div");
  actionRow.className = "veksha-action-row";

  const explainBtn = document.createElement("button");
  explainBtn.className = "veksha-explain-btn";
  explainBtn.textContent = t("content_explain", "More details");

  const listenBtn = document.createElement("button");
  listenBtn.className = "veksha-listen-btn";
  listenBtn.title = t("content_listen", "Listen");
  listenBtn.setAttribute("aria-label", listenBtn.title);
  listenBtn.innerHTML = '<span aria-hidden="true">🔊</span>';
  listenBtn.disabled = true;

  const secondaryActions = document.createElement("div");
  secondaryActions.className = "veksha-secondary-actions";
  secondaryActions.append(listenBtn, explainBtn);
  actionRow.append(secondaryActions);

  const explainBox = document.createElement("div");
  explainBox.className = "veksha-explain";
  explainBox.hidden = true;

  popup.append(header, resultBox, actionRow, explainBox);

  let currentText = selectedText;
  let currentTranslation = "";
  let currentDetectedSource = state.sourceLang === "auto" ? "" : state.sourceLang;

  listenBtn.addEventListener("click", () => {
    speakText(currentTranslation, state.targetLang);
  });

  explainBtn.addEventListener("click", () => {
    requestExplanation(currentText, currentTranslation, explainBox, explainBtn);
  });

  const runTranslation = (text: string) => {
    if (!text?.trim()) { resultBox.textContent = ""; return; }
    currentText = text;
    currentTranslation = "";
    listenBtn.disabled = true;
    explainBox.hidden = true;
    explainBox.textContent = "";
    requestTranslation(text, state.sourceLang, state.targetLang, resultBox, sourceSelect, (tr, detected) => {
      currentTranslation = tr;
      currentDetectedSource = detected ?? (state.sourceLang === "auto" ? "" : state.sourceLang);
      listenBtn.disabled = !tr || !canSpeak();

      // If the source is the user's native language, redo the translation INTO
      // the studied language instead (once).
      const det = (detected || "").toLowerCase();
      if (!flipped && det && studiedLang &&
          studiedLang.toLowerCase() !== nativeLang.toLowerCase() &&
          det === nativeLang.toLowerCase() &&
          state.targetLang.toLowerCase() === nativeLang.toLowerCase()) {
        flipped = true;
        state.targetLang = studiedLang;
        targetSelect.value = studiedLang;
        runTranslation(currentText);
      }
    });
  };

  sourceSelect.addEventListener("change", () => {
    state.sourceLang = sourceSelect.value;
    currentDetectedSource = state.sourceLang === "auto" ? "" : state.sourceLang;
    runTranslation(currentText);
  });
  targetSelect.addEventListener("change", () => {
    state.targetLang = targetSelect.value;
    runTranslation(currentText);
  });
  swapBtn.addEventListener("click", () => {
    const reverseTarget = state.sourceLang === "auto" ? currentDetectedSource : state.sourceLang;
    if (!reverseTarget || !currentTranslation) return;
    state.sourceLang = state.targetLang;
    state.targetLang = reverseTarget;
    sourceSelect.value = state.sourceLang;
    targetSelect.value = state.targetLang;
    runTranslation(currentTranslation);
  });

  document.documentElement.appendChild(popup);
  makePopupDraggable(popup, header);
  runTranslation(selectedText);
}

/** Let the user drag the popup around by its header. Switches to fixed
 *  positioning on grab so the maths stays simple regardless of scroll. */
function makePopupDraggable(el: HTMLElement, handle: HTMLElement): void {
  handle.style.cursor = "move";
  let drag: { sx: number; sy: number; ox: number; oy: number } | null = null;
  handle.addEventListener("pointerdown", (e) => {
    if ((e.target as HTMLElement).closest("button, select")) return;
    const r = el.getBoundingClientRect();
    el.style.position = "fixed";
    el.style.left = `${r.left}px`;
    el.style.top = `${r.top}px`;
    drag = { sx: e.clientX, sy: e.clientY, ox: r.left, oy: r.top };
    handle.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  handle.addEventListener("pointermove", (e) => {
    if (!drag) return;
    el.style.left = `${drag.ox + e.clientX - drag.sx}px`;
    el.style.top = `${drag.oy + e.clientY - drag.sy}px`;
  });
  const end = () => { drag = null; };
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
}

async function requestTranslation(
  text: string,
  sourceLang: string,
  targetLang: string,
  resultBox: HTMLElement,
  sourceSelect: HTMLSelectElement,
  onResult: (translation: string, detectedSourceLang: string | null) => void
) {
  const requestId = ++translationRequestId;
  resultBox.textContent = t("content_translating", "Translating...");
  resultBox.classList.remove("veksha-error");
  resultBox.classList.add("veksha-result--loading");

  let username: string | null;
  try {
    username = await getUsername();
  } catch (err) {
    if (requestId !== translationRequestId) return;
    resultBox.classList.remove("veksha-result--loading");
    resultBox.textContent = `Error: ${(err as Error).message}`;
    resultBox.classList.add("veksha-error");
    return;
  }
  if (requestId !== translationRequestId) return;
  if (!username) {
    resultBox.classList.remove("veksha-result--loading");
    resultBox.textContent = t("content_no_user", "Open the Veksha popup and enter your name first.");
    resultBox.classList.add("veksha-error");
    return;
  }

  try {
    const response = await quickTranslate(username, text, sourceLang, targetLang);
    if (requestId !== translationRequestId) return;
    resultBox.classList.remove("veksha-result--loading");
    resultBox.textContent = response.translation || "(empty)";
    onResult(response.translation || "", response.detected_source_lang);

    if (sourceLang === "auto" && response.detected_source_lang) {
      const autoOpt = sourceSelect.querySelector('option[value="auto"]') as HTMLOptionElement | null;
      if (autoOpt) {
        autoOpt.textContent = response.detected_source_lang.toUpperCase();
      }
    }
  } catch (err) {
    if (requestId !== translationRequestId) return;
    resultBox.classList.remove("veksha-result--loading");
    resultBox.textContent = `Error: ${(err as Error).message}`;
    resultBox.classList.add("veksha-error");
  }
}

async function requestExplanation(
  text: string,
  translation: string,
  explainBox: HTMLElement,
  explainBtn: HTMLButtonElement
) {
  const username = await getUsername();
  if (!username) {
    explainBox.hidden = false;
    explainBox.textContent = t("content_no_user", "Open the Veksha popup and enter your name first.");
    explainBox.classList.add("veksha-error");
    return;
  }

  explainBox.hidden = false;
  explainBox.classList.remove("veksha-error");
  explainBox.textContent = t("content_translating", "Translating...");
  explainBtn.disabled = true;

  try {
    const response = await explain(username, text, translation);
    explainBox.textContent = response.explanation || "(no explanation)";
  } catch (err) {
    explainBox.textContent = `Error: ${(err as Error).message}`;
    explainBox.classList.add("veksha-error");
  } finally {
    explainBtn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Selection listeners
// ---------------------------------------------------------------------------

function inYouTubeStudyUI(node: EventTarget | null): boolean {
  return !!(node as HTMLElement | null)?.closest?.(YT_STUDY_GUARD_SELECTOR);
}

document.addEventListener("mouseup", (e) => {
  if (icon?.contains(e.target as Node) || popup?.contains(e.target as Node)) return;
  // YouTube captions have their own study-mode popup — stay out of its way.
  if (inYouTubeStudyUI(e.target)) return;
  setTimeout(() => {
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? "";

    if (!text) { removeAll(); lastSelectionText = ""; return; }
    if (text === lastSelectionText && (icon || popup)) return;
    lastSelectionText = text;

    const range = selection!.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    removeAll();
    showIcon(rect, text);
  }, 0);
});

document.addEventListener("mousedown", (e) => {
  if (icon?.contains(e.target as Node) || popup?.contains(e.target as Node)) return;
  if (inYouTubeStudyUI(e.target)) return;
  removeAll();
}, true);

// Note: no "scroll" listener — the icon and popup are positioned in document
// coordinates (scrollX/scrollY + rect) and attached to documentElement, so they
// stay anchored to the selected text and scroll along with the page.
window.addEventListener("resize", () => removeAll());

// ---------------------------------------------------------------------------
// Image region translate (regular pages): press on an <img> and drag to select
// an area → OCR + translate → a page-anchored patch laid on top (scrolls with
// the page, since normal DOM scrolling works here).
// ---------------------------------------------------------------------------

let imgRegion: { x: number; y: number; started: boolean; el: HTMLElement } | null = null;
let imgRegionBox: HTMLElement | null = null;

document.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  const el = e.target as HTMLElement | null;
  if (!el || el.tagName !== "IMG") return;
  if (el.closest(".veksha-popup, .veksha-pdf-patch")) return;
  imgRegion = { x: e.clientX, y: e.clientY, started: false, el };
}, true);

// Block the browser's native image drag while we're selecting a region.
document.addEventListener("dragstart", (e) => { if (imgRegion) e.preventDefault(); }, true);

document.addEventListener("pointermove", (e) => {
  if (!imgRegion) return;
  const dx = e.clientX - imgRegion.x, dy = e.clientY - imgRegion.y;
  if (!imgRegion.started) {
    if (Math.hypot(dx, dy) < 6) return; // ignore a plain click
    imgRegion.started = true;
    imgRegionBox = document.createElement("div");
    imgRegionBox.className = "veksha-img-region-box";
    document.documentElement.appendChild(imgRegionBox);
  }
  const x = Math.min(imgRegion.x, e.clientX), y = Math.min(imgRegion.y, e.clientY);
  imgRegionBox!.style.left = `${x}px`;
  imgRegionBox!.style.top = `${y}px`;
  imgRegionBox!.style.width = `${Math.abs(dx)}px`;
  imgRegionBox!.style.height = `${Math.abs(dy)}px`;
  e.preventDefault();
}, true);

document.addEventListener("pointerup", (e) => {
  if (!imgRegion) return;
  const s = imgRegion;
  imgRegion = null;
  imgRegionBox?.remove();
  imgRegionBox = null;
  if (!s.started) return;
  // Suppress the click that follows a drag (e.g. don't open an image link).
  const killClick = (ev: MouseEvent) => { ev.preventDefault(); ev.stopPropagation(); document.removeEventListener("click", killClick, true); };
  document.addEventListener("click", killClick, true);

  const x = Math.min(s.x, e.clientX), y = Math.min(s.y, e.clientY);
  const w = Math.abs(e.clientX - s.x), h = Math.abs(e.clientY - s.y);
  if (w < 8 || h < 8) return;
  // Anchor the patch to the <img> element so it tracks by DOM position, not
  // by screenshot matching (regular pages scroll the document normally).
  runRegionTranslate({ x, y, w, h }, s.el);
}, true);

// ---------------------------------------------------------------------------
// Training / Lesson overlay — triggered from popup via chrome.tabs.sendMessage
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((msg: Record<string, unknown>) => {
  if (msg.type === "VEKSHA_AGGRESSIVE_REMINDER") {
    showAggressiveReminder(msg);
  } else if (msg.type === "VEKSHA_CLEAR_AGGRESSIVE_REMINDER") {
    removeAggressiveReminder();
  } else if (msg.type === "VEKSHA_OPEN_TRAINING" && typeof msg.username === "string") {
    showTrainingOverlay(msg.username);
  } else if (msg.type === "VEKSHA_OPEN_LESSON_PICKER" && typeof msg.username === "string") {
    showTopicPickerOverlay(msg.username);
  } else if (msg.type === "VEKSHA_OPEN_TUTORIAL" && typeof msg.username === "string") {
    showTutorialOverlay(msg.username);
  } else if (
    msg.type === "VEKSHA_OPEN_LESSON" &&
    typeof msg.username === "string" &&
    typeof msg.topic === "string"
  ) {
    showLessonOverlay(msg.username, msg.topic);
  } else if (msg.type === "VEKSHA_TOGGLE_IMMERSION") {
    setImmersionEnabled(Boolean(msg.enabled));
  } else if (msg.type === "VEKSHA_TRANSLATE_SELECTION" && typeof msg.text === "string") {
    openPopup((msg.text as string).trim(), new DOMRect(lastMouse.x, lastMouse.y, 0, 0), { fixed: true });
  } else if (msg.type === "VEKSHA_OCR_DONE" && typeof msg.requestId === "string") {
    const cb = pdfOcrCallbacks.get(msg.requestId);
    if (cb) {
      pdfOcrCallbacks.delete(msg.requestId);
      cb({
        text: (msg.text as string) || "",
        lines: msg.lines as OcrLine[] | undefined,
        bg: msg.bg as string | undefined,
        tmpl: msg.tmpl as { w: number; h: number; data: number[] } | undefined,
        error: msg.error as string | undefined,
      });
    }
  }
});

// ---------------------------------------------------------------------------
// YouTube subtitle study mode — same contextual translator, player-friendly UI.
// Activates only while the video is paused (see youtube.ts).
// ---------------------------------------------------------------------------

if (/(^|\.)youtube\.com$/.test(location.hostname)) {
  initYouTubeStudy({ getUsername, t, state });
}

// ---------------------------------------------------------------------------
// Page immersion ("comprehensible input") — toggled from the popup, remembered
// across pages via chrome.storage.local.
// ---------------------------------------------------------------------------

initImmersion({ getUsername });
chrome.storage.local.get([CONFIG.STORAGE_KEY_IMMERSION], (res) => {
  if (res[CONFIG.STORAGE_KEY_IMMERSION]) setImmersionEnabled(true);
});

// ---------------------------------------------------------------------------
// PDF region translate (OCR) — Chrome's native PDF viewer keeps text inside an
// isolated plugin, unreachable from the DOM. So instead of reading text we let
// the user draw a box, screenshot that region (via the background), OCR it
// locally (Tesseract in the offscreen doc) and translate the result.
// ---------------------------------------------------------------------------

interface PdfRect { x: number; y: number; w: number; h: number; }
interface OcrLine { text: string; bbox: { x: number; y: number; w: number; h: number }; }
interface OcrResult { text: string; lines?: OcrLine[]; bg?: string; tmpl?: { w: number; h: number; data: number[] }; error?: string; }
const pdfOcrCallbacks = new Map<string, (r: OcrResult) => void>();
let pdfFab: HTMLElement | null = null;
let pdfRegionLayer: HTMLElement | null = null;

function isPdfPage(): boolean {
  return (
    document.contentType === "application/pdf" ||
    !!document.querySelector('embed[type="application/pdf"]') ||
    /\.pdf($|[?#])/i.test(location.pathname + location.search)
  );
}

function ensurePdfFab(): void {
  if (pdfFab || !isPdfPage()) return;
  pdfFab = document.createElement("div");
  pdfFab.className = "veksha-pdf-fab";
  pdfFab.title = t("pdf_translate_region", "Translate an area of the PDF");
  const img = document.createElement("img");
  img.src = chrome.runtime.getURL("icons/icon48.png");
  img.alt = "";
  const label = document.createElement("span");
  label.textContent = t("pdf_translate_region", "Translate area");
  pdfFab.append(img, label);
  pdfFab.addEventListener("click", (e) => { e.stopPropagation(); startPdfRegionMode(); });
  document.documentElement.appendChild(pdfFab);
}

function startPdfRegionMode(): void {
  if (pdfRegionLayer) return;
  const layer = document.createElement("div");
  layer.className = "veksha-pdf-region-layer";

  const hint = document.createElement("div");
  hint.className = "veksha-pdf-region-hint";
  hint.textContent = t("pdf_region_hint", "Drag to select an area, then click the icon");
  layer.appendChild(hint);

  let startX = 0, startY = 0, dragging = false;
  let box: HTMLElement | null = null;

  const onDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    // a fresh drag clears a previous box
    box?.remove();
    dragging = true;
    startX = e.clientX; startY = e.clientY;
    box = document.createElement("div");
    box.className = "veksha-pdf-region-box";
    box.style.left = `${startX}px`;
    box.style.top = `${startY}px`;
    layer.appendChild(box);
  };
  const onMove = (e: PointerEvent) => {
    if (!dragging || !box) return;
    const x = Math.min(startX, e.clientX), y = Math.min(startY, e.clientY);
    box.style.left = `${x}px`;
    box.style.top = `${y}px`;
    box.style.width = `${Math.abs(e.clientX - startX)}px`;
    box.style.height = `${Math.abs(e.clientY - startY)}px`;
  };
  const onUp = (e: PointerEvent) => {
    if (!dragging || !box) return;
    dragging = false;
    const x = Math.min(startX, e.clientX), y = Math.min(startY, e.clientY);
    const w = Math.abs(e.clientX - startX), h = Math.abs(e.clientY - startY);
    if (w < 8 || h < 8) { box.remove(); box = null; return; }
    addRegionGoButton(box, { x, y, w, h });
  };

  const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") cleanupPdfRegion(); };

  layer.addEventListener("pointerdown", onDown);
  layer.addEventListener("pointermove", onMove);
  layer.addEventListener("pointerup", onUp);
  document.addEventListener("keydown", onKey, true);
  (layer as unknown as { _cleanup: () => void })._cleanup = () =>
    document.removeEventListener("keydown", onKey, true);

  pdfRegionLayer = layer;
  document.documentElement.appendChild(layer);
}

function addRegionGoButton(box: HTMLElement, rect: PdfRect): void {
  box.querySelector(".veksha-pdf-region-go")?.remove();
  const go = document.createElement("button");
  go.className = "veksha-pdf-region-go";
  go.title = t("content_translating", "Translate");
  const img = document.createElement("img");
  img.src = chrome.runtime.getURL("icons/icon48.png");
  img.alt = "";
  go.appendChild(img);
  go.addEventListener("pointerdown", (e) => { e.stopPropagation(); });
  go.addEventListener("click", (e) => {
    e.stopPropagation();
    runRegionTranslate(rect);
  });
  box.appendChild(go);
}

function cleanupPdfRegion(): void {
  (pdfRegionLayer as unknown as { _cleanup?: () => void } | null)?._cleanup?.();
  pdfRegionLayer?.remove();
  pdfRegionLayer = null;
}

function runRegionTranslate(rect: PdfRect, anchorEl?: HTMLElement | null): void {
  // Tear down our selection UI first so it isn't captured in the screenshot.
  cleanupPdfRegion();
  if (pdfFab) pdfFab.style.display = "none";
  const restoreFab = () => { if (pdfFab) pdfFab.style.display = ""; };

  // If the region sits on a real DOM element (image on a regular page), remember
  // where it is *relative to that element* so we can re-place the patch by DOM
  // position later instead of matching screenshots.
  let anchor: PatchAnchor | null = null;
  if (anchorEl) {
    const er = anchorEl.getBoundingClientRect();
    if (er.width > 0 && er.height > 0) {
      anchor = {
        el: anchorEl,
        fx: (rect.x - er.left) / er.width,
        fy: (rect.y - er.top) / er.height,
        baseW: er.width,
        clip: scrollClipAncestor(anchorEl),
      };
    }
  }

  const loading = document.createElement("div");
  loading.className = "veksha-pdf-loading";
  loading.style.position = "fixed";
  loading.style.left = `${Math.max(8, Math.min(rect.x, window.innerWidth - 160))}px`;
  loading.style.top = `${Math.min(rect.y + rect.h + 8, window.innerHeight - 40)}px`;
  loading.textContent = t("content_translating", "Translating...");
  document.documentElement.appendChild(loading);

  const requestId = crypto.randomUUID();
  pdfOcrCallbacks.set(requestId, (r) => {
    loading.remove();
    restoreFab();
    const clean = (r.text || "").trim();
    if (r.error || !clean) {
      const note = document.createElement("div");
      note.className = "veksha-pdf-loading";
      note.style.position = "fixed";
      note.style.left = `${Math.max(8, Math.min(rect.x, window.innerWidth - 160))}px`;
      note.style.top = `${Math.min(rect.y + rect.h + 8, window.innerHeight - 40)}px`;
      note.textContent = r.error
        ? `⚠ ${r.error}`
        : t("pdf_no_text", "No text recognized in this area.");
      document.documentElement.appendChild(note);
      setTimeout(() => note.remove(), 3000);
      return;
    }
    const tmpl = r.tmpl && r.tmpl.w > 0 && r.tmpl.h > 0
      ? { w: r.tmpl.w, h: r.tmpl.h, data: new Uint8Array(r.tmpl.data) }
      : null;
    void renderInpaintPatch(rect, r.lines, r.bg, tmpl, anchor);
  });

  // Give the browser a moment to repaint without our overlay, then capture.
  setTimeout(() => {
    chrome.runtime.sendMessage({
      type: "VEKSHA_OCR_CAPTURE",
      requestId,
      rect,
      viewportW: window.innerWidth,
      viewportH: window.innerHeight,
    });
  }, 80);
}

function luminance(rgb: string): number {
  const m = rgb.match(/\d+/g);
  if (!m || m.length < 3) return 255;
  const [r, g, b] = m.map(Number);
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

/** Bidirectional translate: foreign → native; but if the source turns out to be
 *  the user's native language, translate into the studied language instead. */
async function smartTranslate(username: string, text: string): Promise<string> {
  const first = await quickTranslate(username, text, "auto", nativeLang || state.targetLang);
  const det = (first.detected_source_lang || "").toLowerCase();
  if (det && studiedLang && det === (nativeLang || "").toLowerCase() &&
      studiedLang.toLowerCase() !== (nativeLang || "").toLowerCase()) {
    const second = await quickTranslate(username, text, "auto", studiedLang);
    return second.translation || text;
  }
  return first.translation || text;
}

// ---------------------------------------------------------------------------
// Patch tracking. Two strategies depending on where the region came from:
//
//  • DOM-anchored (image regions on regular pages): we bind to the source
//    element and the region's fractional position inside it. A requestAnimation-
//    Frame loop re-reads the element's on-screen rect every frame and pins the
//    (position: fixed) patch to it — so it follows the element no matter what
//    moves it: page scroll, an inner overflow-scroll container, sticky/fixed
//    layout, zoom or an animation. It hides when the element is clipped out of
//    its scroll container or leaves the viewport.
//
//  • Screenshot-anchored (PDF native viewer): we can't read the plugin's scroll
//    or reach its DOM, so we remember (by screenshot) what's under each patch,
//    hide patches while the view moves, and after it settles relocate each one
//    by template-matching its snapshot (allowing for a scale/zoom change).
// ---------------------------------------------------------------------------

interface Gray { w: number; h: number; data: Uint8Array; }
interface PatchAnchor { el: HTMLElement; fx: number; fy: number; baseW: number; clip: Element | null; }
interface PatchRec {
  el: HTMLElement;
  tmpl: Gray | null;
  anchor: PatchAnchor | null;
  hidden?: boolean;        // last visibility we applied (avoids redundant restyle)
  lx?: number; ly?: number; ls?: number; // last placed left/top/scale
}

const TRACK_D = 8;                 // downscale factor for matching (must match offscreen's TD)
const FOUND_THRESH = 28;           // match quality below which we accept a location
const activePatches: PatchRec[] = [];
let settleTimer = 0;
let patchesMoving = false;

function captureTab(): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: "VEKSHA_CAPTURE" }, (resp) => {
      const dataUrl = (resp as { dataUrl?: string } | undefined)?.dataUrl;
      if (!dataUrl) { resolve(null); return; }
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = dataUrl;
    });
  });
}

function canvasToGray(c: HTMLCanvasElement): Gray {
  const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
  const g = new Uint8Array(c.width * c.height);
  for (let i = 0, p = 0; p < g.length; p++, i += 4) g[p] = (d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114) | 0;
  return { w: c.width, h: c.height, data: g };
}

function grayAt(img: HTMLImageElement, w: number, h: number): Gray {
  const c = document.createElement("canvas");
  c.width = Math.max(1, w); c.height = Math.max(1, h);
  c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
  return canvasToGray(c);
}

function sceneFromImage(img: HTMLImageElement): { gray: Gray; cssScale: number } {
  return {
    gray: grayAt(img, Math.round(img.naturalWidth / TRACK_D), Math.round(img.naturalHeight / TRACK_D)),
    cssScale: img.naturalWidth / window.innerWidth,
  };
}

function grayToCanvas(g: Gray): HTMLCanvasElement {
  const c = document.createElement("canvas"); c.width = g.w; c.height = g.h;
  const ctx = c.getContext("2d")!; const id = ctx.createImageData(g.w, g.h);
  for (let i = 0, p = 0; p < g.data.length; p++, i += 4) { const v = g.data[p]; id.data[i] = v; id.data[i + 1] = v; id.data[i + 2] = v; id.data[i + 3] = 255; }
  ctx.putImageData(id, 0, 0); return c;
}

function resizeGray(g: Gray, s: number): Gray {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(g.w * s)); c.height = Math.max(1, Math.round(g.h * s));
  c.getContext("2d")!.drawImage(grayToCanvas(g), 0, 0, c.width, c.height);
  return canvasToGray(c);
}

function matchAt(scene: Gray, tmpl: Gray): { x: number; y: number; score: number } {
  let best = Infinity, bx = 0, by = 0;
  const sw = scene.w, sh = scene.h, tw = tmpl.w, th = tmpl.h, sd = scene.data, td = tmpl.data;
  const area = tw * th;
  if (tw > sw || th > sh) return { x: 0, y: 0, score: Infinity };
  for (let oy = 0; oy <= sh - th; oy++) {
    for (let ox = 0; ox <= sw - tw; ox++) {
      let sum = 0; const cap = best * area;
      for (let y = 0; y < th && sum < cap; y++) {
        let s = (oy + y) * sw + ox, tt = y * tw;
        for (let x = 0; x < tw; x++) { const d = sd[s++] - td[tt++]; sum += d < 0 ? -d : d; }
      }
      if (sum < best) { best = sum; bx = ox; by = oy; }
    }
  }
  return { x: bx, y: by, score: best / area };
}

function matchBest(scene: Gray, tmpl: Gray): { x: number; y: number; scale: number; score: number } {
  const base = matchAt(scene, tmpl);
  let best = { x: base.x, y: base.y, scale: 1, score: base.score };
  // Only try other scales when the scale-1 match is ambiguous (a possible zoom).
  // A very poor base means the region scrolled off-screen — don't waste a full
  // multi-scale search on it (that was the main slowdown with several patches).
  if (base.score > 10 && base.score < 40) {
    for (const s of [0.85, 1.18]) {
      const m = matchAt(scene, resizeGray(tmpl, s));
      if (m.score < best.score) best = { x: m.x, y: m.y, scale: s, score: m.score };
    }
  }
  return best;
}

/** The effective stacking z-index of an element: the first explicit z-index on
 *  it or an ancestor, else "auto". Lets a patch layer like its image instead of
 *  floating above the whole page. */
function effectiveZIndex(el: Element): string {
  let n: Element | null = el;
  while (n && n !== document.documentElement) {
    const z = getComputedStyle(n).zIndex;
    if (z && z !== "auto") return z;
    n = n.parentElement;
  }
  return "auto";
}

/** Nearest ancestor that clips/scrolls its content — used to hide a patch when
 *  its element is scrolled out of an inner overflow container. */
function scrollClipAncestor(el: HTMLElement): Element | null {
  let n = el.parentElement;
  while (n && n !== document.body && n !== document.documentElement) {
    const s = getComputedStyle(n);
    if (/(auto|scroll|hidden|clip)/.test(s.overflow + s.overflowX + s.overflowY)) return n;
    n = n.parentElement;
  }
  return null;
}

function setPatchHidden(p: PatchRec, hidden: boolean): void {
  if (p.hidden === hidden) return;
  p.el.style.display = hidden ? "none" : "";
  p.hidden = hidden;
}

/** Pin a DOM-anchored patch to its element's current on-screen position (fixed,
 *  viewport coordinates), scaled to the element's current size. Called every
 *  frame while such patches exist, so it follows whatever moves the element. */
function placeDomPatch(p: PatchRec): void {
  const a = p.anchor;
  if (!a) return;
  if (!a.el.isConnected) { setPatchHidden(p, true); return; }
  const r = a.el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) { setPatchHidden(p, true); return; }
  // Off-screen, or clipped out of an inner scroll container → hide.
  if (r.right <= 0 || r.left >= window.innerWidth || r.bottom <= 0 || r.top >= window.innerHeight) {
    setPatchHidden(p, true); return;
  }
  if (a.clip) {
    const c = a.clip.getBoundingClientRect();
    if (r.right <= c.left || r.left >= c.right || r.bottom <= c.top || r.top >= c.bottom) {
      setPatchHidden(p, true); return;
    }
  }
  const scale = r.width / a.baseW;
  const left = r.left + a.fx * r.width;
  const top = r.top + a.fy * r.height;
  setPatchHidden(p, false);
  if (p.lx === left && p.ly === top && p.ls === scale) return; // unchanged → skip restyle
  p.el.style.left = `${left}px`;
  p.el.style.top = `${top}px`;
  p.el.style.transformOrigin = "top left";
  p.el.style.transform = scale !== 1 ? `scale(${scale})` : "";
  p.lx = left; p.ly = top; p.ls = scale;
}

/** rAF loop pinning every DOM-anchored patch to its element. Runs only while at
 *  least one such patch exists; stops itself otherwise. */
let domRafId = 0;
function domTrackTick(): void {
  let any = false;
  for (const p of activePatches) {
    if (!p.anchor) continue;
    any = true;
    placeDomPatch(p);
  }
  domRafId = any ? requestAnimationFrame(domTrackTick) : 0;
}
function ensureDomTracking(): void {
  if (!domRafId) domRafId = requestAnimationFrame(domTrackTick);
}

function hideScreenshotPatches(): void {
  for (const p of activePatches) if (!p.anchor) p.el.style.visibility = "hidden";
}

async function relocatePatches(img: HTMLImageElement): Promise<void> {
  const { gray: scene, cssScale } = sceneFromImage(img);
  for (const p of activePatches) {
    try {
      if (p.anchor) continue;            // DOM-anchored patches track by element, not screenshot
      if (!p.tmpl) { p.el.style.visibility = ""; continue; }
      const m = matchBest(scene, p.tmpl);
      if (m.score < FOUND_THRESH) {
        p.el.style.left = `${(m.x * TRACK_D) / cssScale}px`;
        p.el.style.top = `${(m.y * TRACK_D) / cssScale}px`;
        p.el.style.transformOrigin = "top left";
        p.el.style.transform = m.scale !== 1 ? `scale(${m.scale})` : "";
        p.el.style.visibility = "";
      } else {
        p.el.style.visibility = "hidden"; // scrolled off-screen / not found
      }
    } catch {
      p.el.style.visibility = ""; // never leave a patch stuck hidden on error
    }
  }
}

/** Screenshot-anchored patches (PDF): on scroll/zoom hide them immediately,
 *  then once the view settles (debounced) screenshot + relocate. DOM-anchored
 *  patches ignore this — they scroll natively as document-absolute elements. */
function markMoved(): void {
  if (!activePatches.some((p) => !p.anchor)) return;
  if (!patchesMoving) { patchesMoving = true; hideScreenshotPatches(); }
  window.clearTimeout(settleTimer);
  settleTimer = window.setTimeout(() => { void settlePatches(); }, 260);
}

async function settlePatches(): Promise<void> {
  patchesMoving = false;
  if (!activePatches.some((p) => !p.anchor)) return;
  const img = await captureTab();
  if (img) await relocatePatches(img);
  else for (const p of activePatches) if (!p.anchor) p.el.style.visibility = ""; // capture failed: just show
}

let patchMoveListenersBound = false;
function ensurePatchTracking(): void {
  if (patchMoveListenersBound) return;
  patchMoveListenersBound = true;
  const opt = { capture: true, passive: true } as AddEventListenerOptions;
  window.addEventListener("wheel", markMoved, opt);
  window.addEventListener("scroll", markMoved, opt);
  window.addEventListener("keydown", markMoved, opt);
  window.addEventListener("resize", markMoved, opt);
}

/** Lay a translated "patch" over the region: each OCR line is covered with the
 *  sampled background colour, and its translation is drawn on top. Tracked either
 *  by DOM anchor (regular-page images) or screenshot matching (PDF); click to
 *  dismiss. */
async function renderInpaintPatch(
  rect: PdfRect,
  lines: OcrLine[] | undefined,
  bg: string | undefined,
  tmpl: Gray | null,
  anchor: PatchAnchor | null,
): Promise<void> {
  const bgc = bg || "rgb(255,255,255)";
  const ink = luminance(bgc) > 140 ? "#111" : "#fff";

  const patch = document.createElement("div");
  patch.className = "veksha-pdf-patch";
  patch.style.width = `${rect.w}px`;
  patch.style.height = `${rect.h}px`;
  // Fill the WHOLE region with the sampled background so no edges of the
  // original letters peek out from under the translation.
  patch.style.background = bgc;
  patch.title = t("pdf_patch_dismiss", "Click to dismiss");
  const rec: PatchRec = { el: patch, tmpl: anchor ? null : tmpl, anchor };
  // Both variants are fixed-positioned; anchored patches get pinned to their
  // element every frame, PDF patches sit at the captured viewport spot.
  patch.style.position = "fixed";
  if (anchor) {
    // Layer like the image rather than above the whole page.
    patch.style.zIndex = effectiveZIndex(anchor.el);
  } else {
    patch.style.left = `${rect.x}px`;
    patch.style.top = `${rect.y}px`;
  }
  patch.addEventListener("click", () => {
    patch.remove();
    const i = activePatches.indexOf(rec);
    if (i >= 0) activePatches.splice(i, 1);
  });
  document.documentElement.appendChild(patch);
  activePatches.push(rec);
  if (anchor) {
    placeDomPatch(rec);   // pin to the element now, then track it every frame
    ensureDomTracking();
  } else {
    ensurePatchTracking(); // scroll listeners drive the screenshot relocate
  }

  const src = lines ?? [];
  // Build the line cells up-front (instant), then fill in translations.
  const spans = src.map((ln) => {
    const cell = document.createElement("div");
    cell.className = "veksha-pdf-patch-line";
    cell.style.left = `${ln.bbox.x}px`;
    cell.style.top = `${ln.bbox.y}px`;
    cell.style.width = `${ln.bbox.w}px`;
    cell.style.height = `${ln.bbox.h}px`;
    const span = document.createElement("span");
    span.className = "veksha-pdf-patch-text";
    span.style.color = ink;
    span.style.fontSize = `${Math.max(9, Math.floor(ln.bbox.h * 0.82))}px`;
    cell.appendChild(span);
    patch.appendChild(cell);
    return span;
  });

  const setLine = (span: HTMLElement, ln: OcrLine, text: string) => {
    span.textContent = text;
    requestAnimationFrame(() => {
      const sw = span.scrollWidth;
      if (sw > ln.bbox.w && sw > 0) span.style.transform = `scaleX(${(ln.bbox.w / sw).toFixed(3)})`;
    });
  };

  const username = await getUsername();
  if (!username || !src.length) return;

  // Single line: one request. Otherwise try a batched request (fast + better
  // context) and split it back; if the translator collapses the newlines and the
  // counts don't match, fall back to translating each line on its own so every
  // cell still gets its matching text (never dump the whole block on line one).
  try {
    if (src.length === 1) {
      setLine(spans[0], src[0], await smartTranslate(username, src[0].text));
    } else {
      const joined = src.map((l) => l.text).join("\n");
      const whole = await smartTranslate(username, joined);
      const parts = whole.split("\n").map((s) => s.trim()).filter((s) => s.length > 0);
      if (parts.length === src.length) {
        src.forEach((ln, i) => setLine(spans[i], ln, parts[i] || ln.text));
      } else {
        const perLine = await Promise.all(src.map((ln) => smartTranslate(username, ln.text)));
        src.forEach((ln, i) => setLine(spans[i], ln, perLine[i] || ln.text));
      }
    }
  } catch {
    src.forEach((ln, i) => setLine(spans[i], ln, ln.text)); // keep originals
  }
}

function onPdfReady(): void {
  ensurePdfFab();
}

// The PDF viewer's <embed> can mount slightly after document_idle — retry a few
// times before giving up.
if (isPdfPage()) {
  onPdfReady();
} else {
  let tries = 0;
  const probe = window.setInterval(() => {
    if (isPdfPage()) { onPdfReady(); window.clearInterval(probe); }
    if (++tries > 10) window.clearInterval(probe);
  }, 500);
}
