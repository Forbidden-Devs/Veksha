/**
 * dualsubs.ts — second subtitle row with the native-language translation.
 *
 * Renders a translated copy of the current caption line right above the
 * original subtitles. Hovering a word in the original highlights the aligned
 * word(s) of the translation (alignment comes from the backend, see
 * /api/subtitles/translate). Toggled by a small chip next to the row;
 * the choice persists in chrome.storage.local.
 *
 * youtube.ts drives this module: it calls sync() whenever the caption line
 * may have changed (mutation observer + periodic tick) and passes the current
 * word spans so token indices always match the interactive captions.
 */
import { subtitleTranslate, type SubtitleTranslation } from "../shared/api";

const STORAGE_KEY = "veksha_dualsubs_on";
const DEBOUNCE_MS = 250;

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
let enabled = false;
let rowEl: HTMLElement | null = null;
let toggleEl: HTMLElement | null = null;

let currentLine = "";          // joined tokens of the line being displayed
let currentResult: SubtitleTranslation | null = null;
let debounceTimer = 0;
let reqSeq = 0;

// Session cache: subtitle lines repeat (rewinds, loops).
const lineCache = new Map<string, SubtitleTranslation>();

export function initDualSubs(d: DualSubsDeps): void {
  deps = d;
  chrome.storage.local.get([STORAGE_KEY], (res) => {
    enabled = Boolean(res[STORAGE_KEY]);
  });
  document.addEventListener("mouseover", onMouseOver, true);
  document.addEventListener("mouseout", onMouseOut, true);
}

// ---------------------------------------------------------------------------
// Line lifecycle (called from youtube.ts)
// ---------------------------------------------------------------------------

/** Keep the row in sync with the current caption words. Cheap when nothing
 *  changed; debounces the backend call while the line is still rolling in. */
export function sync(wordSpans: HTMLElement[], captionRect: DOMRect | null): void {
  ensureToggle(captionRect);
  if (!enabled) {
    hideRow();
    return;
  }
  const tokens = wordSpans.map((w) => (w.textContent ?? "").trim()).filter(Boolean);
  const line = tokens.join(" ");
  if (!line || !captionRect) {
    hideRow();
    currentLine = "";
    return;
  }

  if (line !== currentLine) {
    currentLine = line;
    currentResult = null;
    renderLoading();
    window.clearTimeout(debounceTimer);
    const cached = lineCache.get(line);
    if (cached) {
      currentResult = cached;
      renderResult(cached);
    } else {
      debounceTimer = window.setTimeout(() => void fetchLine(line, tokens), DEBOUNCE_MS);
    }
  }
  positionRow(captionRect);
}

async function fetchLine(line: string, tokens: string[]): Promise<void> {
  const seq = ++reqSeq;
  const username = await deps.getUsername().catch(() => null);
  if (!username || seq !== reqSeq || line !== currentLine) return;
  try {
    const result = await subtitleTranslate(tokens.slice(0, 40), deps.state.sourceLang, deps.state.targetLang);
    lineCache.set(line, result);
    if (seq !== reqSeq || line !== currentLine) return;
    currentResult = result;
    renderResult(result);
  } catch {
    if (seq !== reqSeq || line !== currentLine) return;
    hideRow(); // no translation — don't cover the video with an error row
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
  row.textContent = "…";
  row.hidden = false;
}

function renderResult(result: SubtitleTranslation): void {
  const row = ensureRow();
  if (!row) return;
  row.classList.remove("av-dualsub-loading");
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
// Toggle chip
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
      enabled = !enabled;
      chrome.storage.local.set({ [STORAGE_KEY]: enabled });
      syncToggleFace();
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
