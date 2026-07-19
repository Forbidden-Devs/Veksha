/**
 * dualsubs.ts — second subtitle row with the native-language translation.
 *
 * Renders a translated copy of the current caption line right above the
 * original subtitles. Hovering a word in the original highlights the aligned
 * word(s) of the translation (alignment comes from the backend, see
 * /api/subtitles/translate). Settings enable the feature; while enabled, a
 * small chip next to the row can show or hide translations during playback.
 *
 * youtube.ts normally installs the complete timed-text track at video open and
 * drives it from media time. DOM observation remains a fallback for tracks that
 * YouTube does not expose (for example some live or restricted videos).
 */
import { subtitleTranslate, subtitleTranslateBatch, type SubtitleTranslation } from "../shared/api";
import { CONFIG } from "../shared/config";
import { findCaptionCue, type TimedCaptionCue } from "../shared/youtubeCaptions";

const DEBOUNCE_MS = 250;
const PREFETCH_BATCH_SIZE = 12;
const PREFETCH_LOOK_BEHIND_MS = 30_000;
const PREFETCH_LOOK_AHEAD_MS = 180_000;
const PREFETCH_REFRESH_MS = 60_000;

export interface DualSubsDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
  /** sourceLang is usually "auto"; targetLang is the user's native language. */
  state: { sourceLang: string; targetLang: string };
  /** Player-relative overlay layer (created by youtube.ts). */
  getLayer: () => HTMLElement | null;
  getPlayer: () => HTMLElement | null;
}

let deps: DualSubsDeps;
let featureEnabled = false;
let enabled = false;
let rowEl: HTMLElement | null = null;
let toggleEl: HTMLElement | null = null;

let currentLine = "";          // joined tokens of the line being displayed
let currentResult: SubtitleTranslation | null = null;
let debounceTimer = 0;
let reqSeq = 0;

// Session cache: subtitle lines repeat (rewinds, loops).
const lineCache = new Map<string, SubtitleTranslation>();
let timeline: TimedCaptionCue[] = [];
let translatedTimeline: TimedCaptionCue[] = [];
let preferTimedTranslation = false;
let prefetchGeneration = 0;
let currentPlaybackTimeMs = 0;
let prefetchAnchorTimeMs = Number.NaN;
let requestedPrefetchTimeMs = 0;
let prefetchRequested = false;
let prefetchRunning = false;
const inFlightLines = new Set<string>();
let currentProvisionalLine = "";
let currentProvisionalTokens: string[] = [];

function cacheKey(
  line: string,
  sourceLang = deps.state.sourceLang,
  targetLang = deps.state.targetLang,
): string {
  return `${sourceLang}\u0000${targetLang}\u0000${line}`;
}

export function initDualSubs(d: DualSubsDeps): void {
  deps = d;
  chrome.storage.local.get([
    CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE,
    CONFIG.STORAGE_KEY_DUAL_SUBS,
    CONFIG.STORAGE_KEY_NATIVE_LANG,
  ], (res) => {
    const nativeLang = res[CONFIG.STORAGE_KEY_NATIVE_LANG];
    if (typeof nativeLang === "string" && nativeLang) deps.state.targetLang = nativeLang;
    const storedFeature = res[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE];
    const legacyEnabled = Boolean(res[CONFIG.STORAGE_KEY_DUAL_SUBS]);
    setFeatureEnabled(storedFeature === undefined ? legacyEnabled : Boolean(storedFeature));
    setEnabled(legacyEnabled);
    if (storedFeature === undefined && legacyEnabled) {
      chrome.storage.local.set({ [CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]: true });
    }
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]) {
      setFeatureEnabled(Boolean(changes[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE].newValue));
    }
    if (changes[CONFIG.STORAGE_KEY_DUAL_SUBS]) {
      setEnabled(Boolean(changes[CONFIG.STORAGE_KEY_DUAL_SUBS].newValue));
    }
    if (changes[CONFIG.STORAGE_KEY_NATIVE_LANG]) {
      const target = changes[CONFIG.STORAGE_KEY_NATIVE_LANG].newValue;
      if (typeof target === "string" && target) {
        deps.state.targetLang = target;
        currentLine = "";
        currentResult = null;
        prefetchGeneration += 1;
        requestPrefetch(currentPlaybackTimeMs, true);
      }
    }
  });
  document.addEventListener("mouseover", onMouseOver, true);
  document.addEventListener("mouseout", onMouseOut, true);
}

function setFeatureEnabled(next: boolean): void {
  if (featureEnabled === next) return;
  featureEnabled = next;
  currentLine = "";
  currentResult = null;
  if (!featureEnabled) {
    prefetchGeneration += 1;
    window.clearTimeout(debounceTimer);
    hideRow();
    clearHighlights();
    toggleEl?.remove();
    toggleEl = null;
  } else {
    requestPrefetch(currentPlaybackTimeMs, true);
  }
}

function setEnabled(next: boolean): void {
  if (enabled === next) return;
  enabled = next;
  currentLine = "";
  currentResult = null;
  if (!enabled) {
    prefetchGeneration += 1;
    window.clearTimeout(debounceTimer);
    hideRow();
    clearHighlights();
  }
  syncToggleFace();
  if (enabled) requestPrefetch(currentPlaybackTimeMs, true);
}

// ---------------------------------------------------------------------------
// Line lifecycle (called from youtube.ts)
// ---------------------------------------------------------------------------

/** Keep the row in sync with the current caption words. Cheap when nothing
 *  changed; debounces the backend call while the line is still rolling in. */
export function sync(wordSpans: HTMLElement[], captionRect: DOMRect | null): void {
  syncTokens(
    wordSpans.map((word) => (word.textContent ?? "").trim()).filter(Boolean),
    captionRect,
  );
}

/** Install the complete timed-text track as soon as a YouTube video opens. */
export function setTimeline(
  cues: TimedCaptionCue[],
  translatedCues: TimedCaptionCue[] = [],
  preferTranslatedTimeline = false,
): void {
  timeline = cues;
  translatedTimeline = translatedCues;
  preferTimedTranslation = preferTranslatedTimeline && translatedCues.length > 0;
  currentLine = "";
  currentResult = null;
  currentProvisionalLine = "";
  currentProvisionalTokens = [];
  prefetchAnchorTimeMs = Number.NaN;
  prefetchGeneration += 1;
  // Wait for the first media-time tick. Reusing the previous video's time here
  // could spend one batch on the wrong part of a newly opened video.
}

/** Synchronize from media time, independently of YouTube's frequently replaced caption DOM. */
export function syncAtTime(timeMs: number, captionRect: DOMRect | null): void {
  if (!timeline.length) return;
  currentPlaybackTimeMs = Math.max(0, timeMs);
  requestPrefetch(currentPlaybackTimeMs);
  const cue = findCaptionCue(timeline, timeMs);
  const translatedCue = findCaptionCue(translatedTimeline, timeMs);
  syncTokens(
    cue?.tokens ?? [],
    cue ? captionRect : null,
    translatedCue?.tokens ?? [],
  );
}

function syncTokens(
  tokens: string[],
  captionRect: DOMRect | null,
  provisionalTokens: string[] = [],
): void {
  if (!featureEnabled) {
    hideRow();
    return;
  }
  ensureToggle(captionRect);
  if (!enabled) {
    hideRow();
    return;
  }
  const line = tokens.join(" ");
  if (!line || !captionRect) {
    hideRow();
    currentLine = "";
    currentProvisionalLine = "";
    currentProvisionalTokens = [];
    return;
  }

  const provisionalLine = provisionalTokens.join(" ");

  if (line !== currentLine) {
    currentLine = line;
    currentResult = null;
    currentProvisionalLine = provisionalLine;
    currentProvisionalTokens = provisionalTokens;
    window.clearTimeout(debounceTimer);
    const useTimedTranslation = preferTimedTranslation && provisionalTokens.length > 0;
    const cached = useTimedTranslation ? undefined : lineCache.get(cacheKey(line));
    if (useTimedTranslation) {
      renderTokens(provisionalTokens, true);
    } else if (cached) {
      currentResult = cached;
      renderResult(cached);
    } else {
      if (provisionalTokens.length) renderTokens(provisionalTokens, true);
      else renderLoading();
      // A YouTube-translated authored cue is a stable, immediate fallback.
      // The rolling batch queue will improve upcoming cues without issuing a
      // duplicate single-line request for the cue that is already on screen.
      if (!useTimedTranslation && !provisionalTokens.length) {
        debounceTimer = window.setTimeout(() => void fetchLine(line, tokens), DEBOUNCE_MS);
      }
    }
  } else if (!currentResult && provisionalLine && provisionalLine !== currentProvisionalLine) {
    currentProvisionalLine = provisionalLine;
    currentProvisionalTokens = provisionalTokens;
    renderTokens(provisionalTokens, true);
  }
  positionRow(captionRect);
}

async function fetchLine(line: string, tokens: string[]): Promise<void> {
  const seq = ++reqSeq;
  const sourceLang = deps.state.sourceLang;
  const targetLang = deps.state.targetLang;
  const key = cacheKey(line, sourceLang, targetLang);
  if (lineCache.has(key) || inFlightLines.has(key)) return;
  const username = await deps.getUsername().catch(() => null);
  if (!username || seq !== reqSeq || line !== currentLine) return;
  if (lineCache.has(key) || inFlightLines.has(key)) return;
  inFlightLines.add(key);
  try {
    const result = await subtitleTranslate(tokens.slice(0, 40), sourceLang, targetLang);
    lineCache.set(key, result);
    if (seq !== reqSeq || line !== currentLine) return;
    if (sourceLang !== deps.state.sourceLang || targetLang !== deps.state.targetLang) return;
    if (currentProvisionalTokens.length) return; // keep the visible cue stable; cache for the next visit
    currentResult = result;
    renderResult(result);
  } catch {
    if (seq !== reqSeq || line !== currentLine) return;
    if (currentProvisionalTokens.length) renderTokens(currentProvisionalTokens, true);
    else hideRow();
  } finally {
    inFlightLines.delete(key);
  }
}

function requestPrefetch(timeMs: number, force = false): void {
  if (!featureEnabled || !enabled || !timeline.length) return;
  if (preferTimedTranslation && translatedTimeline.length) return;
  const movedBeyondWindow = !Number.isFinite(prefetchAnchorTimeMs)
    || timeMs < prefetchAnchorTimeMs - PREFETCH_LOOK_BEHIND_MS
    || timeMs > prefetchAnchorTimeMs + PREFETCH_REFRESH_MS;
  if (!force && !movedBeyondWindow) return;

  requestedPrefetchTimeMs = Math.max(0, timeMs);
  prefetchRequested = true;
  prefetchAnchorTimeMs = requestedPrefetchTimeMs;
  if (!prefetchRunning) void runPrefetchLoop();
}

function pendingLinesForWindow(
  timeMs: number,
  sourceLang: string,
  targetLang: string,
): Array<[string, string[]]> {
  const windowStart = Math.max(0, timeMs - PREFETCH_LOOK_BEHIND_MS);
  const windowEnd = timeMs + PREFETCH_LOOK_AHEAD_MS;
  const nearby = timeline.filter((cue) => cue.endMs >= windowStart && cue.startMs <= windowEnd);

  // Current and future cues matter first. Recent past cues are useful for a
  // small rewind, but should never delay what the viewer is about to hear.
  nearby.sort((a, b) => {
    const aPast = a.endMs < timeMs;
    const bPast = b.endMs < timeMs;
    if (aPast !== bPast) return aPast ? 1 : -1;
    return aPast ? b.startMs - a.startMs : a.startMs - b.startMs;
  });

  const unique = new Map<string, string[]>();
  for (const cue of nearby) {
    if (!cue.tokens.length) continue;
    const line = cue.tokens.join(" ");
    const key = cacheKey(line, sourceLang, targetLang);
    if (!lineCache.has(key) && !inFlightLines.has(key)) unique.set(line, cue.tokens);
  }
  return Array.from(unique.entries());
}

async function runPrefetchLoop(): Promise<void> {
  if (prefetchRunning) return;
  prefetchRunning = true;
  try {
    while (prefetchRequested) {
      prefetchRequested = false;
      const timeMs = requestedPrefetchTimeMs;
      const generation = prefetchGeneration;
      const sourceLang = deps.state.sourceLang;
      const targetLang = deps.state.targetLang;
      const username = await deps.getUsername().catch(() => null);
      if (!username || generation !== prefetchGeneration) continue;
      if (!featureEnabled || !enabled || !timeline.length) continue;
      if (preferTimedTranslation && translatedTimeline.length) continue;

      const pending = pendingLinesForWindow(timeMs, sourceLang, targetLang);
      for (let offset = 0; offset < pending.length; offset += PREFETCH_BATCH_SIZE) {
        if (generation !== prefetchGeneration || !featureEnabled || !enabled) break;
        // A seek or a sufficiently large playback advance rebuilds the queue
        // around the new position immediately after the one active request.
        if (prefetchRequested) break;
        const batch = pending.slice(offset, offset + PREFETCH_BATCH_SIZE);
        const keys = batch.map(([line]) => cacheKey(line, sourceLang, targetLang));
        keys.forEach((key) => inFlightLines.add(key));
        try {
          const response = await subtitleTranslateBatch(
            batch.map(([, tokens]) => tokens),
            sourceLang,
            targetLang,
          );
          if (generation !== prefetchGeneration) break;
          if (sourceLang !== deps.state.sourceLang || targetLang !== deps.state.targetLang) break;
          batch.forEach(([line], index) => {
            const result = response.lines[index];
            if (result) lineCache.set(cacheKey(line, sourceLang, targetLang), result);
          });
          const current = lineCache.get(cacheKey(currentLine));
          if (current && !currentProvisionalTokens.length) {
            currentResult = current;
            renderResult(current);
          }
        } catch {
          // Keep YouTube's translated track visible. A later window refresh can
          // retry the failed batch without blocking playback.
        } finally {
          keys.forEach((key) => inFlightLines.delete(key));
        }
      }
    }
  } finally {
    prefetchRunning = false;
    // Avoid losing a request scheduled between the last loop check and cleanup.
    if (prefetchRequested) void runPrefetchLoop();
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function ensureRow(): HTMLElement | null {
  const layer = deps.getLayer();
  if (!layer) return null;
  if (rowEl && rowEl.parentElement === layer) return rowEl;
  rowEl?.remove();
  rowEl = document.createElement("div");
  rowEl.className = "av-dualsub";
  layer.appendChild(rowEl);
  return rowEl;
}

function renderLoading(): void {
  const row = ensureRow();
  if (!row) return;
  row.classList.add("av-dualsub-loading");
  row.classList.remove("av-dualsub-provisional");
  row.textContent = "…";
  row.hidden = false;
}

function renderResult(result: SubtitleTranslation): void {
  const row = ensureRow();
  if (!row) return;
  row.classList.remove("av-dualsub-loading");
  row.classList.remove("av-dualsub-provisional");
  row.textContent = "";
  result.translation_tokens.forEach((tok, i) => {
    if (i > 0) row.appendChild(document.createTextNode(" "));
    const span = document.createElement("span");
    span.className = "av-dualsub-word";
    span.dataset.idx = String(i);
    span.textContent = tok;
    row.appendChild(span);
  });
  row.hidden = false;
}

function renderTokens(tokens: string[], provisional: boolean): void {
  const row = ensureRow();
  if (!row) return;
  row.classList.remove("av-dualsub-loading");
  row.classList.toggle("av-dualsub-provisional", provisional);
  row.textContent = "";
  tokens.forEach((token, index) => {
    if (index > 0) row.appendChild(document.createTextNode(" "));
    const span = document.createElement("span");
    span.className = "av-dualsub-word";
    span.dataset.idx = String(index);
    span.textContent = token;
    row.appendChild(span);
  });
  row.hidden = false;
}

function hideRow(): void {
  if (rowEl) rowEl.hidden = true;
}

/** Place the row right above the caption window, centered on it. */
function positionRow(captionRect: DOMRect): void {
  if (!rowEl || rowEl.hidden) return;
  const player = deps.getPlayer();
  if (!player) return;
  const p = player.getBoundingClientRect();
  const rowH = rowEl.offsetHeight;
  const cx = captionRect.left + captionRect.width / 2 - p.left;
  const left = Math.max(8, Math.min(cx - rowEl.offsetWidth / 2, player.clientWidth - rowEl.offsetWidth - 8));
  rowEl.style.left = `${left}px`;
  rowEl.style.top = `${Math.max(8, captionRect.top - p.top - rowH - 8)}px`;
}

// ---------------------------------------------------------------------------
// Hover alignment highlighting
// ---------------------------------------------------------------------------

function srcIndexOf(word: HTMLElement): number {
  const all = Array.from(
    document.querySelectorAll<HTMLElement>(".ytp-caption-window-container .av-yt-word"),
  );
  return all.indexOf(word);
}

function onMouseOver(e: MouseEvent): void {
  if (!enabled || !currentResult || !rowEl || rowEl.hidden) return;
  const word = (e.target as HTMLElement | null)?.closest?.<HTMLElement>(".av-yt-word");
  if (!word) return;
  const idx = srcIndexOf(word);
  if (idx < 0) return;
  const group = currentResult.alignment.find((g) => g.src.includes(idx));
  clearHighlights();
  if (!group) return;
  word.classList.add("av-yt-hl-src");
  for (const di of group.dst) {
    rowEl.querySelector<HTMLElement>(`.av-dualsub-word[data-idx="${di}"]`)?.classList.add("av-dualsub-hl");
  }
}

function onMouseOut(e: MouseEvent): void {
  const word = (e.target as HTMLElement | null)?.closest?.(".av-yt-word");
  if (word) clearHighlights();
}

function clearHighlights(): void {
  document.querySelectorAll(".av-dualsub-hl").forEach((el) => el.classList.remove("av-dualsub-hl"));
  document.querySelectorAll(".av-yt-hl-src").forEach((el) => el.classList.remove("av-yt-hl-src"));
}

// ---------------------------------------------------------------------------
// Per-video toggle chip (available only when the feature is enabled in Settings)
// ---------------------------------------------------------------------------

function ensureToggle(captionRect: DOMRect | null): void {
  const layer = deps.getLayer();
  if (!layer) return;
  if (!toggleEl || toggleEl.parentElement !== layer) {
    toggleEl?.remove();
    toggleEl = document.createElement("button");
    toggleEl.className = "av-dualsub-toggle";
    toggleEl.addEventListener("mousedown", (e) => e.stopPropagation());
    toggleEl.addEventListener("click", (e) => {
      e.stopPropagation();
      const next = !enabled;
      setEnabled(next);
      chrome.storage.local.set({ [CONFIG.STORAGE_KEY_DUAL_SUBS]: next });
      if (!enabled) {
        hideRow();
        clearHighlights();
      } else {
        currentLine = ""; // force re-fetch on next sync tick
      }
    });
    layer.appendChild(toggleEl);
    syncToggleFace();
  }
  // Show the chip only while there are captions to translate.
  toggleEl.hidden = !captionRect;
  if (captionRect) {
    const player = deps.getPlayer();
    if (!player) return;
    const p = player.getBoundingClientRect();
    toggleEl.style.left = `${Math.min(captionRect.right - p.left + 10, player.clientWidth - 40)}px`;
    toggleEl.style.top = `${captionRect.top - p.top + (captionRect.height - 26) / 2}px`;
  }
}

function syncToggleFace(): void {
  if (!toggleEl) return;
  toggleEl.textContent = "";
  const icon = document.createElement("span");
  icon.textContent = enabled ? "🌐" : "🌐";
  toggleEl.classList.toggle("av-dualsub-toggle-on", enabled);
  toggleEl.appendChild(icon);
  toggleEl.title = deps.t("content_dualsubs", "Dual subtitles");
}
