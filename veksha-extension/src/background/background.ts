import { CONFIG } from "../shared/config";
import { getReminders } from "../shared/api";
import { googleLinkAccount, googleSignIn } from "../shared/googleAuth";
import type { RemindersData } from "../shared/types";
import { focusSiteForUrl, sessionBlocksUrl, type FocusSession } from "../shared/focusSession";
import {
  captionTrackJson3Url,
  extractCaptionTracks,
  parseJson3Captions,
  selectCaptionTrack,
} from "../shared/youtubeCaptions";

// Google-link outcome persisted for the Settings screen: the popup usually
// closes as soon as the OAuth window takes focus, so the result must survive
// until the popup is opened again.
const GOOGLE_LINK_RESULT_KEY = "vk_google_link_result";
const CAPTURE_KEY_PREFIX = "vk_region_capture_";

/** Runs in YouTube's MAIN world so signed caption URLs use the exact player
 * response, cookies and visitor state of the video being watched. Keep this
 * function self-contained: chrome.scripting serializes it into the page. */
async function readYouTubeCaptionsInPage(sourceLang: string, targetLang: string) {
  type Track = { baseUrl: string; languageCode: string; kind?: string; vssId?: string };
  type Player = HTMLElement & {
    getPlayerResponse?: () => {
      captions?: { playerCaptionsTracklistRenderer?: {
        captionTracks?: Track[];
        audioTracks?: { captionTrackIndices?: number[]; defaultCaptionTrackIndex?: number }[];
        defaultAudioTrackIndex?: number;
      } };
    };
    getOption?: (module: string, option: string) => { languageCode?: string; kind?: string; vssId?: string } | null;
  };
  const player = document.getElementById("movie_player") as Player | null;
  const initial = (globalThis as typeof globalThis & {
    ytInitialPlayerResponse?: ReturnType<NonNullable<Player["getPlayerResponse"]>>;
  }).ytInitialPlayerResponse;
  const response = player?.getPlayerResponse?.() ?? initial;
  const renderer = response?.captions?.playerCaptionsTracklistRenderer;
  const tracks = renderer?.captionTracks ?? [];
  if (!tracks.length) return { ok: false, retryable: !player, error: "caption-tracks-unavailable" };

  const baseLanguage = (code: string) => code.toLowerCase().split(/[-_]/)[0];
  const active = player?.getOption?.("captions", "track");
  let candidates: Track[] = [];
  if (active?.vssId) candidates = tracks.filter((track) => track.vssId === active.vssId);
  if (!candidates.length && active?.languageCode) {
    candidates = tracks.filter((track) =>
      track.languageCode.toLowerCase() === active.languageCode?.toLowerCase()
      && (!active.kind || track.kind === active.kind));
  }
  if (!candidates.length && sourceLang && sourceLang !== "auto") {
    const exact = tracks.filter((track) => track.languageCode.toLowerCase() === sourceLang.toLowerCase());
    const sameBase = tracks.filter((track) => baseLanguage(track.languageCode) === baseLanguage(sourceLang));
    candidates = exact.length ? exact : sameBase;
  }
  if (!candidates.length) {
    const audioIndex = renderer?.defaultAudioTrackIndex ?? 0;
    const audio = renderer?.audioTracks?.[audioIndex];
    const indices = audio?.captionTrackIndices ?? [];
    candidates = indices.map((index) => tracks[index]).filter(Boolean);
    const defaultTrack = audio?.defaultCaptionTrackIndex;
    if (typeof defaultTrack === "number" && tracks[defaultTrack]) {
      candidates = [tracks[defaultTrack], ...candidates.filter((track) => track !== tracks[defaultTrack])];
    }
  }
  if (!candidates.length) candidates = tracks;
  const firstLanguage = baseLanguage(candidates[0].languageCode);
  const sameLanguage = candidates.filter((track) => baseLanguage(track.languageCode) === firstLanguage);
  const track = sameLanguage.find((item) => item.kind !== "asr") ?? sameLanguage[0];
  if (!track) return { ok: false, error: "caption-track-unavailable" };

  const load = async (translatedTo?: string) => {
    const url = new URL(track.baseUrl);
    url.searchParams.set("fmt", "json3");
    if (translatedTo) url.searchParams.set("tlang", translatedTo);
    const result = await fetch(url.toString(), { credentials: "include" });
    if (!result.ok) throw new Error(`caption HTTP ${result.status}`);
    const text = await result.text();
    if (!text.trim()) throw new Error("empty caption response");
    return JSON.parse(text) as unknown;
  };

  const sourcePayload = await load();
  let translatedPayload: unknown = null;
  if (targetLang && targetLang !== "auto" && baseLanguage(targetLang) !== baseLanguage(track.languageCode)) {
    try { translatedPayload = await load(targetLang); } catch { /* LLM remains the fallback */ }
  }
  return {
    ok: true,
    sourcePayload,
    translatedPayload,
    track: { languageCode: track.languageCode, kind: track.kind === "asr" ? "asr" : "manual" },
  };
}

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
const LAST_REMINDER_AT_KEY = "veksha-last-reminder-at";
const REMINDER_INTERVAL_MS = 12 * 60 * 60 * 1000;

async function getStoredUsername(): Promise<string | null> {
  const values = await chrome.storage.local.get(CONFIG.STORAGE_KEY_USERNAME);
  const stored = values[CONFIG.STORAGE_KEY_USERNAME];
  return typeof stored === "string" && stored ? stored : null;
}

const CTX_TRANSLATE_ID = "veksha-translate-selection";
const CTX_TRANSLATE_AREA_ID = "veksha-translate-area";
async function openRegionCapture(windowId: number): Promise<void> {
  const image = await chrome.tabs.captureVisibleTab(windowId, { format: "png" });
  const token = crypto.randomUUID();
  const key = `${CAPTURE_KEY_PREFIX}${token}`;
  await chrome.storage.session.set({ [key]: { image, expiresAt: Date.now() + 2 * 60 * 1000 } });
  await chrome.tabs.create({ url: chrome.runtime.getURL(`src/capture/index.html#${token}`) });
}

async function deliverSelection(tabId: number, text: string): Promise<void> {
  const payload = { type: "VEKSHA_TRANSLATE_SELECTION", text };
  try {
    await chrome.tabs.sendMessage(tabId, payload);
    return;
  } catch {
    const target = { tabId };
    await chrome.scripting.executeScript({ target, files: ["src/content/content.js"] });
    await chrome.scripting.insertCSS({ target, files: ["src/content/content.css"] });
    await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 150));
    await chrome.tabs.sendMessage(tabId, payload);
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(CONFIG.REMINDERS_ALARM_NAME, {
    periodInMinutes: CONFIG.REMINDERS_INTERVAL_MINUTES,
  });
  chrome.contextMenus.removeAll(() => {
    const entries: chrome.contextMenus.CreateProperties[] = [
      { id: CTX_TRANSLATE_ID, title: "Translate selection with Veksha", contexts: ["selection"] },
      { id: CTX_TRANSLATE_AREA_ID, title: "Translate an area with Veksha", contexts: ["page", "image"] },
    ];
    entries.forEach((entry) => chrome.contextMenus.create(entry));
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === CTX_TRANSLATE_AREA_ID && tab?.windowId !== undefined) {
    try { await openRegionCapture(tab.windowId); } catch {}
    return;
  }
  if (info.menuItemId !== CTX_TRANSLATE_ID || !tab?.id) return;
  const text = (info.selectionText ?? "").trim();
  if (!text) return;
  await deliverSelection(tab.id, text).catch(() => undefined);
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== CONFIG.REMINDERS_ALARM_NAME) return;

  const username = await getStoredUsername();
  if (!username) return;

  try {
    const result = await getReminders(username);
    if (result.should_remind) await displayReminder(result);
  } catch {}
});

async function displayReminder(result: RemindersData, force = false) {
  if (!force && !(await shouldShowReminderNow())) return;

  // Review reminders are notifications only. Full-page intervention belongs
  // exclusively to a deliberately started Study Focus Session.
  showReminderNotification(result);
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  const url = changeInfo.url ?? tab.url;
  if (!url || url.startsWith(chrome.runtime.getURL("src/focus/index.html"))) return;
  void chrome.storage.local.get([CONFIG.STORAGE_KEY_FOCUS_SESSION]).then(async (values) => {
    const session = values[CONFIG.STORAGE_KEY_FOCUS_SESSION] as FocusSession | undefined;
    if (!session) return;
    if (session.endsAt <= Date.now()) {
      await chrome.storage.local.remove([CONFIG.STORAGE_KEY_FOCUS_SESSION]);
      return;
    }
    if (!sessionBlocksUrl(session, url)) return;
    const site = focusSiteForUrl(url);
    if (!site) return;
    const gate = chrome.runtime.getURL("src/focus/index.html")
      + `?target=${encodeURIComponent(url)}&site=${encodeURIComponent(site)}`;
    await chrome.tabs.update(tabId, { url: gate });
  });
});

function showReminderNotification(result: Pick<RemindersData, "due_words" | "due_goal">) {
  const wordNote = result.due_words
    ? `${result.due_words} ${result.due_words === 1 ? "word" : "words"} to review`
    : "";
  const goalNote = result.due_goal ? `objective “${result.due_goal}” waiting` : "";
  const due = [wordNote, goalNote].filter(Boolean).join(" · ");

  const notification: chrome.notifications.NotificationOptions<true> = {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: "Time to practice! \u{1F4AA}",
    message: due || "Your scheduled practice is ready.",
  };
  chrome.notifications.create(NOTIFICATION_ID, notification);
}

function openReminderFromNotification(notificationId: string): void {
  if (notificationId !== NOTIFICATION_ID) return;
  void chrome.notifications.clear(notificationId);
  chrome.action?.openPopup?.().catch(() => {});
}

chrome.notifications.onClicked.addListener(openReminderFromNotification);

chrome.runtime.onMessage.addListener((msg: Record<string, unknown>, _sender, sendResponse) => {
  if (msg.type === "VEKSHA_START_REGION_CAPTURE") {
    chrome.tabs.query({ active: true, currentWindow: true })
      .then(([tab]) => {
        if (tab?.windowId === undefined) throw new Error("no active tab");
        return openRegionCapture(tab.windowId);
      })
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }
  if (msg.type === "VEKSHA_GET_REGION_CAPTURE") {
    const token = typeof msg.token === "string" ? msg.token : "";
    const key = `${CAPTURE_KEY_PREFIX}${token}`;
    chrome.storage.session.get([key]).then(async (values) => {
      await chrome.storage.session.remove([key]);
      const capture = values[key] as { image?: string; expiresAt?: number } | undefined;
      const image = capture && Number(capture.expiresAt) > Date.now() ? capture.image ?? "" : "";
      sendResponse({ ok: Boolean(image), image });
    }).catch(() => sendResponse({ ok: false, image: "" }));
    return true;
  }
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

  if (msg.type === "VEKSHA_YOUTUBE_CAPTIONS") {
    const videoId = typeof msg.videoId === "string" ? msg.videoId : "";
    const sourceLang = typeof msg.sourceLang === "string" ? msg.sourceLang : "auto";
    const targetLang = typeof msg.targetLang === "string" ? msg.targetLang : "";
    if (!/^[\w-]{6,20}$/.test(videoId)) {
      sendResponse({ ok: false, error: "invalid-video-id" });
      return false;
    }
    (async () => {
      const tabId = _sender.tab?.id;
      if (tabId !== undefined) {
        try {
          const injected = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",
            func: readYouTubeCaptionsInPage,
            args: [sourceLang, targetLang],
          });
          const pageResult = injected[0]?.result as {
            ok?: boolean;
            retryable?: boolean;
            sourcePayload?: unknown;
            translatedPayload?: unknown;
            track?: { languageCode: string; kind: string };
          } | undefined;
          if (pageResult?.ok && pageResult.sourcePayload) {
            return {
              ok: true,
              cues: parseJson3Captions(pageResult.sourcePayload),
              translatedCues: parseJson3Captions(pageResult.translatedPayload),
              track: pageResult.track ?? null,
            };
          }
          if (pageResult?.retryable) return { ok: false, retryable: true, error: "player-not-ready" };
        } catch {
          // Older browser builds may not support MAIN-world execution. The
          // signed watch-page fallback below preserves compatibility.
        }
      }

      const watchUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}&hl=en`;
      const page = await fetch(watchUrl, { credentials: "include" });
      if (!page.ok) throw new Error(`YouTube watch page returned HTTP ${page.status}`);
      const tracks = extractCaptionTracks(await page.text());
      const track = selectCaptionTrack(tracks, sourceLang);
      if (!track) return { ok: true, cues: [], track: null };
      const timedUrl = captionTrackJson3Url(track.baseUrl);
      const parsedUrl = new URL(timedUrl);
      if (!/(^|\.)youtube\.com$/.test(parsedUrl.hostname)) {
        throw new Error("unexpected YouTube caption host");
      }
      const timed = await fetch(timedUrl, { credentials: "include" });
      if (!timed.ok) throw new Error(`YouTube captions returned HTTP ${timed.status}`);
      const cues = parseJson3Captions(await timed.json());
      let translatedCues: ReturnType<typeof parseJson3Captions> = [];
      if (targetLang && targetLang !== "auto" && targetLang.split("-")[0] !== track.languageCode.split("-")[0]) {
        try {
          const translatedUrl = captionTrackJson3Url(track.baseUrl, targetLang);
          const translated = await fetch(translatedUrl, { credentials: "include" });
          if (translated.ok) translatedCues = parseJson3Captions(await translated.json());
        } catch {
          // The source timeline is still useful; LLM prefetch remains available.
        }
      }
      return {
        ok: true,
        cues,
        translatedCues,
        track: {
          languageCode: track.languageCode,
          kind: track.kind === "asr" ? "asr" : "manual",
        },
      };
    })()
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: String((err as Error).message ?? err) }));
    return true;
  }

  return false;
});

async function shouldShowReminderNow(): Promise<boolean> {
  const stored = await chrome.storage.local.get([LAST_REMINDER_AT_KEY])
    .catch(() => ({}) as Record<string, unknown>);
  const last = Number((stored as Record<string, unknown>)[LAST_REMINDER_AT_KEY] ?? 0);
  const now = Date.now();
  if (last && now - last < REMINDER_INTERVAL_MS) return false;

  await chrome.storage.local.set({ [LAST_REMINDER_AT_KEY]: now }).catch(() => {});
  return true;
}
