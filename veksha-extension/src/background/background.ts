import { CONFIG } from "../shared/config";
import { getReminders, getSettings } from "../shared/api";
import { googleLinkAccount, googleSignIn } from "../shared/googleAuth";
import type { RemindersData } from "../shared/types";
import type { CaptureController } from "../shared/capture";

// Google-link outcome persisted for the Settings screen: the popup usually
// closes as soon as the OAuth window takes focus, so the result must survive
// until the popup is opened again.
const GOOGLE_LINK_RESULT_KEY = "vk_google_link_result";

// WebSocket proxy for session windows (Firefox build): extension pages can
// have plain ws:// blocked by profile security settings, while this event
// page opens it reliably. The page connects a Port (see shared/wsProxy.ts)
// and the socket lives here; the port closing closes the socket and vice
// versa.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "veksha-ws") return;
  let ws: WebSocket | null = null;
  const wsBase = CONFIG.BACKEND_URL.replace(/^http/, "ws");

  port.onMessage.addListener((msg: Record<string, unknown>) => {
    if (msg.type === "ws_connect" && !ws) {
      const url = String(msg.url || "");
      if (!url.startsWith(`${wsBase}/`)) {
        try { port.postMessage({ type: "ws_error" }); } catch { /* page gone */ }
        port.disconnect();
        return;
      }
      ws = new WebSocket(url);
      ws.onopen = () => { try { port.postMessage({ type: "ws_open" }); } catch { ws?.close(); } };
      ws.onmessage = (e) => { try { port.postMessage({ type: "ws_message", data: e.data as string }); } catch { ws?.close(); } };
      ws.onerror = () => { try { port.postMessage({ type: "ws_error" }); } catch { /* page gone */ } };
      ws.onclose = () => { try { port.postMessage({ type: "ws_close" }); } catch { /* page gone */ } };
    } else if (msg.type === "ws_send") {
      if (ws?.readyState === WebSocket.OPEN) ws.send(String(msg.data ?? ""));
    } else if (msg.type === "ws_close") {
      ws?.close();
    }
  });

  port.onDisconnect.addListener(() => {
    ws?.close();
    ws = null;
  });
});

const NOTIFICATION_ID = "veksha-reminder";
const OFFSCREEN_DOCUMENT_PATH = "src/offscreen/offscreen.html";
const LAST_REMINDER_AT_KEY = "veksha-last-reminder-at";
// Level 1-2: at most once per 12h. Level 3 ("frequent"): at most once per hour.
const NORMAL_REMINDER_INTERVAL_MS = 12 * 60 * 60 * 1000;
const FREQUENT_REMINDER_INTERVAL_MS = 60 * 60 * 1000;

// Chrome backgrounds are service workers and must delegate OCR to an
// offscreen document. Firefox has no offscreen API, but its MV3 background
// is an event page with DOM access — run the capture controller right here.
// Build-time constant: on Chrome the whole direct-capture path (including the
// tesseract.js import below) is tree-shaken out of the service worker.
const supportsOffscreen = __BROWSER__ === "chrome";
let creatingOffscreen: Promise<void> | null = null;

let localCapturePromise: Promise<CaptureController> | null = null;

function getLocalCapture(): Promise<CaptureController> {
  if (!localCapturePromise) {
    localCapturePromise = import("../shared/capture").then((m) =>
      m.createCaptureController((msg) => {
        if (msg.type === "OCR_RESULT" || msg.type === "OCR_ERROR") relayOcrResult(msg);
      }),
    );
  }
  return localCapturePromise;
}

// OCR-region requests in flight: requestId -> originating tab.
const ocrRequests = new Map<string, number>();

async function handleOcrCapture(
  requestId: string,
  rect: unknown,
  viewportW: number,
  viewportH: number,
  tab?: chrome.tabs.Tab,
): Promise<void> {
  if (!tab?.id) return;
  ocrRequests.set(requestId, tab.id);
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
    const payload = { type: "OCR_REGION", requestId, dataUrl, rect, viewportW, viewportH };
    if (supportsOffscreen) {
      await ensureOffscreenDocument();
      await chrome.runtime.sendMessage({ target: "offscreen", ...payload });
    } else {
      const capture = await getLocalCapture();
      void capture.handleOcrRegion(payload);
    }
  } catch (err) {
    ocrRequests.delete(requestId);
    chrome.tabs.sendMessage(tab.id, { type: "VEKSHA_OCR_DONE", requestId, error: String(err) }).catch(() => {});
  }
}

function relayOcrResult(msg: Record<string, unknown>): void {
  const requestId = String(msg.requestId || "");
  const tabId = ocrRequests.get(requestId);
  if (tabId === undefined) return;
  ocrRequests.delete(requestId);
  chrome.tabs.sendMessage(tabId, {
    type: "VEKSHA_OCR_DONE",
    requestId,
    text: typeof msg.text === "string" ? msg.text : "",
    lines: msg.lines,
    bg: msg.bg,
    tmpl: msg.tmpl,
    error: typeof msg.error === "string" ? msg.error : undefined,
  }).catch(() => {});
}

function getStoredUsername(): Promise<string | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get([CONFIG.STORAGE_KEY_USERNAME], (result) => {
      resolve((result[CONFIG.STORAGE_KEY_USERNAME] as string) || null);
    });
  });
}

const CTX_TRANSLATE_ID = "veksha-translate-selection";
const FIRST_REVIEW_ALARM = "veksha-first-review";
const FIRST_WORDS_KEY = "vk_first_words";
const FIRST_REVIEW_SCHEDULED_KEY = "vk_first_review_scheduled";

/** After the user's first 3 translated words, call them back for a short
 *  review half an hour later — the "come close the loop" nudge. */
async function handleFirstWordSaved(): Promise<void> {
  const st = await chrome.storage.local.get([FIRST_WORDS_KEY, FIRST_REVIEW_SCHEDULED_KEY]);
  if (st[FIRST_REVIEW_SCHEDULED_KEY]) return;
  const n = ((st[FIRST_WORDS_KEY] as number) || 0) + 1;
  await chrome.storage.local.set({ [FIRST_WORDS_KEY]: n });
  if (n >= 3) {
    chrome.alarms.create(FIRST_REVIEW_ALARM, { delayInMinutes: 30 });
    await chrome.storage.local.set({ [FIRST_REVIEW_SCHEDULED_KEY]: true });
  }
}

async function fireFirstReview(): Promise<void> {
  const username = await getStoredUsername();
  if (!username) return;
  try {
    const result = await getReminders(username);
    await displayReminder(username, result, true);
  } catch {
    chrome.notifications.create("veksha-first-review-note", {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Time to review! 💪",
      message: "Your first words are ready for a quick training.",
    });
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(CONFIG.REMINDERS_ALARM_NAME, {
    periodInMinutes: CONFIG.REMINDERS_INTERVAL_MINUTES,
  });
  // Right-click "Translate" on selected text — the reliable way to grab text
  // from places the page DOM can't reach (e.g. Chrome's built-in PDF viewer).
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: CTX_TRANSLATE_ID,
      title: "Translate selection with Veksha",
      contexts: ["selection"],
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== CTX_TRANSLATE_ID || !tab?.id) return;
  const text = (info.selectionText ?? "").trim();
  if (!text) return;
  const message = { type: "VEKSHA_TRANSLATE_SELECTION", text };
  try {
    await chrome.tabs.sendMessage(tab.id, message);
  } catch {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["src/content/content.js"] });
      await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["src/content/content.css"] });
      await new Promise<void>((resolve) => setTimeout(resolve, 150));
      await chrome.tabs.sendMessage(tab.id, message);
    } catch {}
  }
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === FIRST_REVIEW_ALARM) {
    await fireFirstReview();
    return;
  }
  if (alarm.name !== CONFIG.REMINDERS_ALARM_NAME) return;

  const username = await getStoredUsername();
  if (!username) return;

  try {
    const result = await getReminders(username);
    if (result.should_remind) await displayReminder(username, result);
  } catch {}
});

async function displayReminder(username: string, result: RemindersData, force = false) {
  let level = 2;
  let overseer = false;
  try {
    const settings = await getSettings(username);
    level = settings.reminder_level ?? 2;
    overseer = settings.overseer ?? false;
  } catch {}
  if (!force && !(await shouldShowReminderNow(level))) return;

  // Level 1+: plain system notification.
  showReminderNotification(result);
  // Level 2+: in-page pop-up with page blur (and optional overseer behaviour).
  if (level < 2) return;

  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id || !tab.url || /^(chrome|chrome-extension|moz-extension|about):/.test(tab.url)) return;

  const message = {
    type: "VEKSHA_AGGRESSIVE_REMINDER",
    username,
    due_words: result.due_words,
    due_word_names: result.due_word_names ?? [],
    due_topic: result.due_topic,
    overseer,
  };
  try {
    await chrome.tabs.sendMessage(tab.id, message);
  } catch {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["src/content/content.js"] });
      await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["src/content/content.css"] });
      await new Promise<void>((resolve) => setTimeout(resolve, 150));
      await chrome.tabs.sendMessage(tab.id, message);
    } catch {}
  }
}

function showReminderNotification(result: { due_words: number; due_topic: string | null; due_word_names?: string[] }) {
  const parts: string[] = [];
  if (result.due_words > 0) parts.push(`${result.due_words} word${result.due_words === 1 ? "" : "s"} to review`);
  if (result.due_topic) parts.push(`an unfinished topic "${result.due_topic}"`);
  const message = parts.length ? `You have ${parts.join(" and ")}.` : "You have words to review.";

  chrome.notifications.create(NOTIFICATION_ID, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: "Time to practice! \u{1F4AA}",
    message,
  });
}

chrome.notifications.onClicked.addListener((notificationId) => {
  if (notificationId !== NOTIFICATION_ID) return;
  chrome.notifications.clear(notificationId);
  chrome.action?.openPopup?.().catch(() => {});
});

chrome.runtime.onMessage.addListener((msg: Record<string, unknown>, _sender, sendResponse) => {
  if (msg.type === "VEKSHA_GOOGLE_SIGNIN") {
    // The whole OAuth flow runs here (not in the popup): the popup dies when
    // the auth window takes focus, the background survives. Credentials are
    // persisted before responding, so even a dead popup ends up signed in.
    (async () => {
      const resp = await googleSignIn();
      await chrome.storage.local.set({
        [CONFIG.STORAGE_KEY_USERNAME]: resp.username,
        [CONFIG.STORAGE_KEY_TOKEN]: resp.token,
        [CONFIG.STORAGE_KEY_GOOGLE_SIGNIN_RESULT]: {
          username: resp.username,
          display_name: resp.display_name,
          created: resp.created,
          ts: Date.now(),
        },
      });
      return resp;
    })()
      .then((resp) => sendResponse({
        ok: true,
        username: resp.username,
        display_name: resp.display_name,
        created: resp.created,
      }))
      .catch((err) => sendResponse({ ok: false, error: String((err as Error).message ?? err) }));
    return true;
  }

  if (msg.type === "VEKSHA_GOOGLE_LINK") {
    (async () => {
      try {
        const res = await googleLinkAccount();
        const result = { ok: true, email: res.email };
        await chrome.storage.local.set({ [GOOGLE_LINK_RESULT_KEY]: result });
        sendResponse(result);
      } catch (err) {
        const m = String((err as Error).message ?? err);
        const error = m === "google-cancelled" ? "cancelled" : m === "google-taken" ? "taken" : "failed";
        // A cancelled window is not worth reporting after the fact.
        if (error !== "cancelled") {
          await chrome.storage.local.set({ [GOOGLE_LINK_RESULT_KEY]: { ok: false, error } });
        }
        sendResponse({ ok: false, error });
      }
    })();
    return true;
  }

  if (msg.type === "VEKSHA_API_FETCH") {
    // Backend fetch proxy for content scripts: their own fetch() runs with
    // the page's privileges (blocked by site CSP in Firefox, page CORS in
    // Chrome); the background is not subject to either.
    const path = typeof msg.path === "string" ? msg.path : "";
    if (!path.startsWith("/")) {
      sendResponse({ ok: false, status: 0, body: "", error: `bad path: ${path.slice(0, 100)}` });
      return false;
    }
    const timeoutMs = typeof msg.timeoutMs === "number" ? msg.timeoutMs : 30_000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    fetch(`${CONFIG.BACKEND_URL}${path}`, {
      method: typeof msg.method === "string" ? msg.method : "GET",
      headers: (msg.headers as Record<string, string>) ?? {},
      body: typeof msg.body === "string" ? msg.body : undefined,
      signal: controller.signal,
    })
      .then(async (res) => sendResponse({ ok: res.ok, status: res.status, body: await res.text() }))
      .catch((err) => sendResponse({
        ok: false,
        status: 0,
        body: "",
        error: (err as Error).name === "AbortError"
          ? `timed out after ${Math.round(timeoutMs / 1000)}s`
          : String(err),
      }))
      .finally(() => clearTimeout(timer));
    return true; // async
  }

  if (msg.type === "VEKSHA_CAPTURE") {
    const tab = _sender.tab;
    if (!tab?.id) { sendResponse({ error: "no-tab" }); return false; }
    chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 85 })
      .then((dataUrl) => sendResponse({ dataUrl }))
      .catch((err) => sendResponse({ error: String(err) }));
    return true; // async
  }

  if (msg.type === "VEKSHA_WORD_SAVED") {
    void handleFirstWordSaved();
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "VEKSHA_OCR_CAPTURE") {
    handleOcrCapture(
      String(msg.requestId || ""),
      msg.rect,
      Number(msg.viewportW) || 0,
      Number(msg.viewportH) || 0,
      _sender.tab,
    );
    sendResponse({ ok: true });
    return false;
  }

  if (msg.target === "background" && (msg.type === "OCR_RESULT" || msg.type === "OCR_ERROR")) {
    relayOcrResult(msg);
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "DEBUG_SHOW_REMINDER") {
    const result = msg.reminder as { due_words: number; due_word_names?: string[]; due_topic: string | null; should_remind: boolean };
    // Debug button: always fire the reminder so the user can test notifications,
    // regardless of whether words are actually due (should_remind).
    getStoredUsername()
      .then((username) => {
        if (!username) return;
        return displayReminder(username, {
          ...result,
          due_word_names: result.due_word_names ?? [],
          poll_interval_minutes: CONFIG.REMINDERS_INTERVAL_MINUTES,
        } as RemindersData, true);
      })
      .then(() => sendResponse({ ok: true, shown: true }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  return false;
});

async function ensureOffscreenDocument() {
  const offscreen = chrome.offscreen;
  if (!offscreen) throw new Error("chrome.offscreen is unavailable");

  const offscreenUrl = chrome.runtime.getURL(OFFSCREEN_DOCUMENT_PATH);
  const contexts = await chrome.runtime.getContexts({
    contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
    documentUrls: [offscreenUrl],
  });
  if (contexts.length > 0) return;

  // Chrome allows only one offscreen document, so concurrent createDocument
  // calls must share one promise.
  if (!creatingOffscreen) {
    creatingOffscreen = offscreen.createDocument({
      url: OFFSCREEN_DOCUMENT_PATH,
      reasons: [chrome.offscreen.Reason.DOM_PARSER],
      justification: "Run OCR on captured screenshots for Veksha translations.",
    }).finally(() => { creatingOffscreen = null; });
  }
  await creatingOffscreen;
}

async function shouldShowReminderNow(level: number): Promise<boolean> {
  const interval = level >= 3 ? FREQUENT_REMINDER_INTERVAL_MS : NORMAL_REMINDER_INTERVAL_MS;
  const stored = await chrome.storage.local.get([LAST_REMINDER_AT_KEY]).catch(() => ({}) as Record<string, unknown>);
  const last = Number((stored as Record<string, unknown>)[LAST_REMINDER_AT_KEY] ?? 0);
  const now = Date.now();
  if (last && now - last < interval) return false;

  await chrome.storage.local.set({ [LAST_REMINDER_AT_KEY]: now }).catch(() => {});
  return true;
}
