/**
 * youtube.ts — always-on subtitle study mode for YouTube.
 *
 * This is the same contextual translator as the page-wide selection flow,
 * adapted to the video-player format. The captions are ALWAYS interactive —
 * there is no icon to press and no mode to toggle:
 *
 *   1. Caption words are kept wrapped in clickable spans (playing or paused).
 *   2. Click a word, or press-and-drag across several → every word the cursor
 *      passes over is highlighted and translated together, in a frosted popup
 *      floating above the subtitles with a source→target language row,
 *      🔊 listen and details.
 *
 * Resuming playback / seeking just clears the current popup and selection;
 * the new caption line stays interactive.
 */
import { quickTranslate, explain } from "../shared/api";
import { canSpeak, speakText } from "../shared/speech";
import { LANGUAGES } from "../shared/languages";

export interface YouTubeStudyDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
  state: { sourceLang: string; targetLang: string };
}

const SEL = {
  player: ".html5-video-player",
  captionContainer: ".ytp-caption-window-container",
  captionWindow: ".caption-window",
  segment: ".ytp-caption-segment",
} as const;

// Anything that belongs to our own UI or to the captions we made interactive.
// content.ts uses this to keep the page-wide selection popup out of the way.
export const YT_STUDY_GUARD_SELECTOR =
  ".ytp-caption-window-container, .av-yt-layer, .av-yt-popup";

let deps: YouTubeStudyDeps;

let layer: HTMLElement | null = null;
let popupEl: HTMLElement | null = null;

let reqId = 0;

// Hover-drag word selection state.
let dragging = false;

// Proactively keep caption words wrapped as YouTube re-renders the line.
let wrapTimer = 0;
let captionObserver: MutationObserver | null = null;
let observedContainer: HTMLElement | null = null;

// ---------------------------------------------------------------------------
// DOM lookups (queried lazily — YouTube is an SPA and re-renders constantly)
// ---------------------------------------------------------------------------

function getPlayer(): HTMLElement | null {
  return document.querySelector<HTMLElement>(SEL.player);
}

function getSegments(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(`${SEL.captionContainer} ${SEL.segment}`)
  );
}

/** Convert a viewport rect into coordinates relative to the player's box. */
function relCoords(rect: DOMRect): { left: number; top: number; right: number; bottom: number; cx: number } {
  const p = getPlayer()?.getBoundingClientRect();
  const ox = p?.left ?? 0;
  const oy = p?.top ?? 0;
  return {
    left: rect.left - ox,
    top: rect.top - oy,
    right: rect.right - ox,
    bottom: rect.bottom - oy,
    cx: rect.left + rect.width / 2 - ox,
  };
}

/** The overlay layer lives inside the player so it survives fullscreen. */
function ensureLayer(): HTMLElement | null {
  const player = getPlayer();
  if (!player) return null;
  if (layer && layer.parentElement === player) return layer;
  layer?.remove();
  layer = document.createElement("div");
  layer.className = "av-yt-layer";
  player.appendChild(layer);
  return layer;
}

// ---------------------------------------------------------------------------
// Always-on selectable captions
// ---------------------------------------------------------------------------

/** Mark EVERY caption window interactive (pointer-events + selectable). YouTube
 *  spins up a fresh .caption-window per line while playing, so tagging just one
 *  leaves newly-loaded lines dead — tag them all. */
function markCaptionsInteractive(): void {
  const windows = document.querySelectorAll<HTMLElement>(SEL.captionWindow);
  if (windows.length) {
    windows.forEach((w) => w.classList.add("av-yt-captions"));
  } else {
    document.querySelector<HTMLElement>(SEL.captionContainer)?.classList.add("av-yt-captions");
  }
}

/** Make sure the current caption line is wrapped + marked interactive. */
function ensureCaptionsInteractive(): void {
  if (!document.querySelector(SEL.captionContainer)) return;
  wrapWords();
  markCaptionsInteractive();
  syncCaptionObserver();
}

/** Watch the caption container so words are re-wrapped the instant YouTube
 *  changes the subtitles — not only on a hover or the periodic tick. The
 *  container is recreated across navigations/toggles, so we re-attach whenever
 *  a new one shows up. */
function syncCaptionObserver(): void {
  const container = document.querySelector<HTMLElement>(SEL.captionContainer);
  if (!container) {
    captionObserver?.disconnect();
    captionObserver = null;
    observedContainer = null;
    return;
  }
  if (captionObserver && observedContainer === container) return; // already watching it
  captionObserver?.disconnect();
  observedContainer = container;
  captionObserver = new MutationObserver(onCaptionMutation);
  captionObserver.observe(container, { childList: true, subtree: true, characterData: true });
}

/** Re-wrap on any caption change. We pause the observer around our own edits so
 *  wrapping doesn't re-trigger it in a loop. */
function onCaptionMutation(): void {
  if (!captionObserver || !observedContainer) return;
  captionObserver.disconnect();
  wrapWords();
  markCaptionsInteractive();
  captionObserver.observe(observedContainer, { childList: true, subtree: true, characterData: true });
}

/** A segment needs (re)wrapping when it has no word spans yet, OR it has spans
 *  but also raw non-space text directly inside it — which happens constantly
 *  with rolling captions, where YouTube appends new words to an already-wrapped
 *  segment. A stale "already wrapped" check would leave those new words dead. */
function segmentNeedsWrap(seg: HTMLElement): boolean {
  if (!seg.querySelector(".av-yt-word")) return true;
  for (const child of Array.from(seg.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE && (child.textContent ?? "").trim() !== "") return true;
  }
  return false;
}

/** Wrap each whitespace-delimited token in a clickable span. Idempotent for a
 *  stable line; re-wraps the whole segment whenever YouTube changed its text. */
function wrapWords(): void {
  for (const seg of getSegments()) {
    if (!segmentNeedsWrap(seg)) continue;
    const text = seg.textContent ?? "";
    if (!text.trim()) continue;
    const frag = document.createDocumentFragment();
    for (const tok of text.split(/(\s+)/)) {
      if (!tok) continue;
      if (/^\s+$/.test(tok)) {
        frag.appendChild(document.createTextNode(tok));
      } else {
        const w = document.createElement("span");
        w.className = "av-yt-word";
        w.textContent = tok;
        frag.appendChild(w);
      }
    }
    seg.textContent = "";
    seg.appendChild(frag);
  }
}

function clearWordHighlights(): void {
  document.querySelectorAll(".av-yt-word.av-yt-selected").forEach((el) => el.classList.remove("av-yt-selected"));
}

function stripEdges(s: string): string {
  return s.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "").trim();
}

/** Build language <option>s (codes only — matches the page-wide translator). */
function buildLangOptions(sel: HTMLSelectElement, selected: string, includeAuto: boolean): void {
  sel.innerHTML = "";
  for (const lang of LANGUAGES) {
    if (!includeAuto && lang.code === "auto") continue;
    const opt = document.createElement("option");
    opt.value = lang.code;
    opt.textContent = lang.code === "auto" ? "AUTO" : lang.code.toUpperCase();
    if (lang.code === selected) opt.selected = true;
    sel.appendChild(opt);
  }
}

/** Smallest rect covering every element (viewport coords). */
function unionRect(els: HTMLElement[]): DOMRect {
  const rects = els.map((el) => el.getBoundingClientRect());
  const left = Math.min(...rects.map((r) => r.left));
  const top = Math.min(...rects.map((r) => r.top));
  const right = Math.max(...rects.map((r) => r.right));
  const bottom = Math.max(...rects.map((r) => r.bottom));
  return new DOMRect(left, top, right - left, bottom - top);
}

/** Selected words, in reading order, joined into a phrase. */
function selectedPhrase(): { text: string; words: HTMLElement[] } {
  const words = Array.from(
    document.querySelectorAll<HTMLElement>(`${SEL.captionContainer} .av-yt-word.av-yt-selected`)
  );
  const raw = words.length === 1
    ? words[0].textContent ?? ""
    : words.map((w) => w.textContent ?? "").join(" ");
  return { text: stripEdges(raw), words };
}

// ---------------------------------------------------------------------------
// Caption interaction → translation popup
// ---------------------------------------------------------------------------

/** Is the cursor currently over any subtitle box? Tested by coordinates (not
 *  event.target) so it works even before the captions become interactive. */
function pointerOverCaptions(x: number, y: number): boolean {
  let boxes = Array.from(document.querySelectorAll<HTMLElement>(SEL.captionWindow));
  if (!boxes.length) {
    const c = document.querySelector<HTMLElement>(SEL.captionContainer);
    if (c) boxes = [c];
  }
  return boxes.some((el) => {
    const r = el.getBoundingClientRect();
    return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  });
}

/** Debug: log the selectable caption words under the cursor, only when the set
 *  actually changes (mousemove fires far too often to log every time). */
let lastLoggedWords = "";
function logCaptionWords(): void {
  const words = Array.from(
    document.querySelectorAll<HTMLElement>(`${SEL.captionContainer} .av-yt-word`)
  ).map((w) => w.textContent ?? "");
  const key = words.join("|");
  if (key === lastLoggedWords) return;
  lastLoggedWords = key;
  console.log("[Veksha][yt] caption words:", words);
}

/** On every move over the subs, make sure the current line is wrapped so any
 *  word is clickable. Cheap: a rect test + an idempotent wrap. While dragging,
 *  also light up each word the cursor passes over. */
function onDocMouseMove(e: MouseEvent): void {
  if (pointerOverCaptions(e.clientX, e.clientY)) {
    ensureCaptionsInteractive();
    logCaptionWords();
  }
  if (!dragging) return;
  const target = e.target as HTMLElement | null;
  const word = target?.closest?.<HTMLElement>(".av-yt-word");
  if (word && !word.classList.contains("av-yt-selected")) {
    word.classList.add("av-yt-selected");
  }
}

/** Finish a drag (or a single click) → translate the highlighted words. */
function onDocMouseUp(e: MouseEvent): void {
  if (!dragging) return;
  dragging = false;
  e.stopPropagation();

  const { text, words } = selectedPhrase();
  if (!text || !words.length) return;
  openPopup(text, unionRect(words));
}

function openPopup(text: string, anchor: DOMRect): void {
  const root = ensureLayer();
  if (!root) return;
  removePopup();

  popupEl = document.createElement("div");
  popupEl.className = "av-yt-popup";
  popupEl.addEventListener("mousedown", (e) => e.stopPropagation());
  popupEl.addEventListener("mouseup", (e) => e.stopPropagation());

  // Language row (source → target), mirrors the page-wide translator.
  const header = document.createElement("div");
  header.className = "av-yt-header";
  const langRow = document.createElement("div");
  langRow.className = "av-yt-lang-row";

  const sourceSelect = document.createElement("select");
  sourceSelect.className = "av-yt-select";
  buildLangOptions(sourceSelect, deps.state.sourceLang, true);

  const swapBtn = document.createElement("button");
  swapBtn.className = "av-yt-swap";
  swapBtn.title = "Swap languages";
  swapBtn.textContent = "→";

  const targetSelect = document.createElement("select");
  targetSelect.className = "av-yt-select";
  buildLangOptions(targetSelect, deps.state.targetLang, false);

  langRow.append(sourceSelect, swapBtn, targetSelect);
  header.append(langRow);

  const orig = document.createElement("div");
  orig.className = "av-yt-orig";
  orig.textContent = text;

  const translation = document.createElement("div");
  translation.className = "av-yt-translation av-yt-loading";
  translation.textContent = deps.t("content_translating", "Translating...");

  const actions = document.createElement("div");
  actions.className = "av-yt-actions";

  const listenBtn = document.createElement("button");
  listenBtn.className = "av-yt-listen";
  listenBtn.title = deps.t("content_listen", "Listen");
  listenBtn.setAttribute("aria-label", listenBtn.title);
  listenBtn.innerHTML = '<span aria-hidden="true">🔊</span>';
  listenBtn.disabled = true;

  const breakdownBtn = document.createElement("button");
  breakdownBtn.className = "av-yt-breakdown";
  breakdownBtn.textContent = deps.t("content_explain", "More details");

  actions.append(listenBtn, breakdownBtn);

  const explainBox = document.createElement("div");
  explainBox.className = "av-yt-explain";
  explainBox.hidden = true;

  const pointer = document.createElement("div");
  pointer.className = "av-yt-pointer";

  popupEl.append(header, orig, translation, actions, explainBox, pointer);
  root.appendChild(popupEl);

  let currentText = text;
  let currentTranslation = "";
  let currentDetected = deps.state.sourceLang === "auto" ? "" : deps.state.sourceLang;

  const retranslate = () => {
    currentTranslation = "";
    listenBtn.disabled = true;
    explainBox.hidden = true;
    explainBox.textContent = "";
    translation.className = "av-yt-translation av-yt-loading";
    translation.textContent = deps.t("content_translating", "Translating...");
    orig.textContent = currentText;
    runTranslation(currentText, translation, (tr, detected) => {
      currentTranslation = tr;
      currentDetected = detected ?? (deps.state.sourceLang === "auto" ? "" : deps.state.sourceLang);
      listenBtn.disabled = !tr || !canSpeak();
      if (deps.state.sourceLang === "auto" && detected) {
        const autoOpt = sourceSelect.querySelector<HTMLOptionElement>('option[value="auto"]');
        if (autoOpt) autoOpt.textContent = detected.toUpperCase();
      }
      positionPopup(anchor);
    });
  };

  sourceSelect.addEventListener("change", (e) => {
    e.stopPropagation();
    deps.state.sourceLang = sourceSelect.value;
    retranslate();
  });
  targetSelect.addEventListener("change", (e) => {
    e.stopPropagation();
    deps.state.targetLang = targetSelect.value;
    retranslate();
  });
  swapBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const reverseTarget = deps.state.sourceLang === "auto" ? currentDetected : deps.state.sourceLang;
    if (!reverseTarget || !currentTranslation) return;
    deps.state.sourceLang = deps.state.targetLang;
    deps.state.targetLang = reverseTarget;
    buildLangOptions(sourceSelect, deps.state.sourceLang, true);
    buildLangOptions(targetSelect, deps.state.targetLang, false);
    currentText = currentTranslation;
    retranslate();
  });

  listenBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (currentTranslation) speakText(currentTranslation, deps.state.targetLang);
  });
  breakdownBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    runBreakdown(currentText, currentTranslation, explainBox, breakdownBtn, anchor);
  });

  retranslate();

  positionPopup(anchor);
  requestAnimationFrame(() => popupEl?.classList.add("av-yt-show"));
}

/** Float the popup above the anchor, clamped to the player width. */
function positionPopup(anchor: DOMRect): void {
  if (!popupEl) return;
  const r = relCoords(anchor);
  const playerW = getPlayer()?.clientWidth ?? window.innerWidth;
  const w = popupEl.offsetWidth;
  const h = popupEl.offsetHeight;
  const gap = 14;

  let left = r.cx - w / 2;
  left = Math.max(8, Math.min(left, playerW - w - 8));
  const top = r.top - h - gap;

  popupEl.style.left = `${left}px`;
  popupEl.style.top = `${Math.max(8, top)}px`;

  // keep the tail pointing at the anchor even after horizontal clamping
  const pointer = popupEl.querySelector<HTMLElement>(".av-yt-pointer");
  if (pointer) {
    const tail = Math.max(14, Math.min(r.cx - left, w - 14));
    pointer.style.left = `${tail - 7}px`;
  }
}

function removePopup(): void {
  popupEl?.remove();
  popupEl = null;
}

async function runTranslation(
  text: string,
  out: HTMLElement,
  onDone: (translation: string, detectedSourceLang: string | null) => void
): Promise<void> {
  const id = ++reqId;
  let username: string | null = null;
  try {
    username = await deps.getUsername();
  } catch {
    username = null;
  }
  if (id !== reqId || !popupEl) return;
  if (!username) {
    out.classList.remove("av-yt-loading");
    out.textContent = deps.t("content_no_user", "Open the Veksha popup and enter your name first.");
    return;
  }
  try {
    const resp = await quickTranslate(username, text, deps.state.sourceLang, deps.state.targetLang);
    if (id !== reqId || !popupEl) return;
    out.classList.remove("av-yt-loading");
    out.textContent = resp.translation || "—";
    onDone(resp.translation || "", resp.detected_source_lang ?? null);
  } catch (err) {
    if (id !== reqId || !popupEl) return;
    out.classList.remove("av-yt-loading");
    out.textContent = `⚠ ${(err as Error).message}`;
  }
}

async function runBreakdown(
  text: string,
  translation: string,
  box: HTMLElement,
  btn: HTMLButtonElement,
  anchor: DOMRect
): Promise<void> {
  const username = await deps.getUsername().catch(() => null);
  if (!popupEl) return;
  if (!username) {
    box.hidden = false;
    box.textContent = deps.t("content_no_user", "Open the Veksha popup and enter your name first.");
    positionPopup(anchor);
    return;
  }
  box.hidden = false;
  box.textContent = deps.t("content_translating", "Translating...");
  btn.disabled = true;
  positionPopup(anchor);
  try {
    const resp = await explain(username, text, translation);
    if (!popupEl) return;
    box.textContent = resp.explanation || "—";
  } catch (err) {
    if (!popupEl) return;
    box.textContent = `⚠ ${(err as Error).message}`;
  } finally {
    btn.disabled = false;
    // re-anchor: the popup grew taller, keep the tail on the subs
    positionPopup(anchor);
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

/** Drop the current popup + selection (the caption line is changing). */
function clearTransient(): void {
  dragging = false;
  removePopup();
  clearWordHighlights();
}

function onPlay(e: Event): void {
  // The line will change as playback resumes — drop stale popup/selection,
  // but captions stay interactive (the wrap loop re-wraps the new line).
  if (!(e.target instanceof HTMLVideoElement)) return;
  clearTransient();
}

function onSeeking(e: Event): void {
  // Seeking swaps the caption line under us — drop stale popup/selection.
  if (!(e.target instanceof HTMLVideoElement)) return;
  clearTransient();
}

function onDocMouseDown(e: MouseEvent): void {
  const target = e.target as HTMLElement | null;
  if (target?.closest(SEL.captionContainer)) {
    // Start a hover-drag word selection. Block native text-drag (the "subtitle
    // shadow") and the player's click-to-pause.
    e.preventDefault();
    e.stopPropagation();
    removePopup();
    clearWordHighlights();
    // Make sure the freshest line is wrapped so the click lands on a word
    // even right after YouTube re-rendered the caption.
    ensureCaptionsInteractive();
    dragging = true;
    const word = (e.target as HTMLElement | null)?.closest<HTMLElement>(".av-yt-word");
    if (word) word.classList.add("av-yt-selected");
    return;
  }
  if (target?.closest(".av-yt-popup")) return;
  // click elsewhere → just dismiss the popup
  removePopup();
  clearWordHighlights();
}

let initialized = false;

export function initYouTubeStudy(d: YouTubeStudyDeps): void {
  if (initialized) return;
  initialized = true;
  deps = d;

  // Media events don't bubble, but the capture phase still reaches the
  // document — so these survive YouTube's SPA navigations without re-binding.
  document.addEventListener("play", onPlay, true);
  document.addEventListener("seeking", onSeeking, true);

  document.addEventListener("mousedown", onDocMouseDown, true);
  document.addEventListener("mousemove", onDocMouseMove, true);
  document.addEventListener("mouseup", onDocMouseUp, true);

  window.addEventListener("resize", removePopup);
  document.addEventListener("fullscreenchange", () => {
    // the player box moved/resized; rebuild overlay on next interaction
    layer?.remove();
    layer = null;
    removePopup();
  });

  // Keep caption words wrapped as YouTube re-renders the line (playing or
  // paused). Cheap: a couple of querySelectors, skipping already-wrapped segs.
  wrapTimer = window.setInterval(ensureCaptionsInteractive, 300);
}
