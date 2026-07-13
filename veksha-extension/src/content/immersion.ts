/**
 * immersion.ts — "comprehensible input" page immersion.
 *
 * When enabled, sentences on the page whose difficulty matches the learner's
 * level (or is one step above — i+1) are replaced inline with their translation
 * in the language being studied, so reading a familiar page sprinkles in a bit
 * of new language. The visible part of the page is processed first; scrolling
 * and dynamic content are picked up incrementally. Per-sentence results are
 * cached on the backend (site + level + language pair), so revisits are instant.
 *
 * DOM strategy: we only ever touch individual Text nodes — a translated
 * sentence is wrapped in a small <span class="av-imm"> while the surrounding
 * text is left untouched, so page markup (links, bold, layout) survives.
 * Disabling restores every original sentence.
 */
import { analyzeImmersion, type ImmersionSentence } from "../shared/api";
import { isVisible, SKIP_CLOSEST, SKIP_TAGS } from "./page-text";

export interface ImmersionDeps {
  getUsername: () => Promise<string | null>;
}

const MIN_CHARS = 40;       // ignore short labels/menus
const BATCH = 24;           // text nodes sent per request
const VIEWPORT_MARGIN = 400; // px above/below the fold to pre-process
const DEBOUNCE_MS = 300;

let deps: ImmersionDeps;
let enabled = false;
let processed = new WeakSet<Text>();
let sessionCache = new Map<string, ImmersionSentence[]>();
let scanTimer: ReturnType<typeof setTimeout> | null = null;
let scanning = false;
let observer: MutationObserver | null = null;

export function initImmersion(d: ImmersionDeps): void {
  deps = d;
}

export function isImmersionEnabled(): boolean {
  return enabled;
}

export function setImmersionEnabled(on: boolean): void {
  if (on === enabled) return;
  enabled = on;
  if (on) {
    window.addEventListener("scroll", scheduleScan, { passive: true });
    window.addEventListener("resize", scheduleScan, { passive: true });
    observer = new MutationObserver(() => scheduleScan());
    observer.observe(document.body, { childList: true, subtree: true });
    scheduleScan();
  } else {
    window.removeEventListener("scroll", scheduleScan);
    window.removeEventListener("resize", scheduleScan);
    observer?.disconnect();
    observer = null;
    if (scanTimer) { clearTimeout(scanTimer); scanTimer = null; }
    restoreAll();
  }
}

function scheduleScan(): void {
  if (!enabled) return;
  if (scanTimer) clearTimeout(scanTimer);
  scanTimer = setTimeout(() => { scanTimer = null; void scan(); }, DEBOUNCE_MS);
}

// ---------------------------------------------------------------------------
// Scanning
// ---------------------------------------------------------------------------

function isTranslatable(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length < MIN_CHARS) return false;
  if (!/\p{L}/u.test(trimmed)) return false;
  return /\s/.test(trimmed); // at least a couple of words
}

function collectNodes(limit: number): Text[] {
  const out: Text[] = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node: Node): number {
      const text = node as Text;
      if (processed.has(text)) return NodeFilter.FILTER_REJECT;
      const parent = text.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      if (parent.isContentEditable) return NodeFilter.FILTER_REJECT;
      if (parent.closest(SKIP_CLOSEST)) return NodeFilter.FILTER_REJECT;
      if (!isTranslatable(text.data)) return NodeFilter.FILTER_REJECT;
      if (!isVisible(parent, VIEWPORT_MARGIN)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (out.length < limit && walker.nextNode()) {
    out.push(walker.currentNode as Text);
  }
  return out;
}

async function scan(): Promise<void> {
  if (!enabled || scanning) return;
  const nodes = collectNodes(BATCH);
  if (!nodes.length) return;

  const username = await deps.getUsername().catch(() => null);
  if (!username || !enabled) return;

  scanning = true;
  try {
    // Mark up-front so overlapping scans don't double-send the same nodes.
    nodes.forEach((n) => processed.add(n));

    // Serve from session cache where we can; only ask the server for the rest.
    const need: { node: Text; text: string }[] = [];
    const ready: { node: Text; sentences: ImmersionSentence[] }[] = [];
    for (const node of nodes) {
      const text = node.data;
      const cached = sessionCache.get(text);
      if (cached) ready.push({ node, sentences: cached });
      else need.push({ node, text });
    }

    if (need.length) {
      const resp = await analyzeImmersion(username, need.map((n) => n.text));
      if (!enabled) return;
      resp.blocks.forEach((block, i) => {
        const { node, text } = need[i];
        sessionCache.set(text, block.sentences);
        ready.push({ node, sentences: block.sentences });
      });
    }

    if (!enabled) return;
    withObserverPaused(() => {
      for (const { node, sentences } of ready) applyToNode(node, sentences);
    });
  } catch (err) {
    console.debug("[immersion] scan failed:", err);
  } finally {
    scanning = false;
    // New content may have scrolled into view while we were waiting.
    if (enabled && collectNodes(1).length) scheduleScan();
  }
}

// ---------------------------------------------------------------------------
// DOM application / restoration
// ---------------------------------------------------------------------------

function makeMarker(translation: string, original: string, cefr: string): HTMLElement {
  const span = document.createElement("span");
  span.className = "av-imm";
  span.textContent = translation;
  span.dataset.avOrig = original;
  if (cefr) span.dataset.avCefr = cefr;
  span.title = original;
  return span;
}

/** Replace each translated sentence inside a single text node with a marker. */
function applyToNode(node: Text, sentences: ImmersionSentence[]): void {
  if (!node.isConnected || !node.parentNode) return;
  const translatable = sentences.filter((s) => s.translation && s.translation.trim());
  if (!translatable.length) return;

  const original = node.data;
  const frag = document.createDocumentFragment();
  let cursor = 0;
  let changed = false;

  for (const s of translatable) {
    const idx = original.indexOf(s.text, cursor);
    if (idx < 0) continue; // sentence not found verbatim — leave it be
    if (idx > cursor) frag.appendChild(document.createTextNode(original.slice(cursor, idx)));
    frag.appendChild(makeMarker(s.translation.trim(), s.text, s.cefr));
    cursor = idx + s.text.length;
    changed = true;
  }
  if (!changed) return;
  if (cursor < original.length) frag.appendChild(document.createTextNode(original.slice(cursor)));

  // The leftover (untranslated) text nodes shouldn't be reconsidered.
  frag.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) processed.add(child as Text);
  });
  node.parentNode.replaceChild(frag, node);
}

function restoreAll(): void {
  withObserverPaused(() => {
    const markers = document.querySelectorAll<HTMLElement>(".av-imm");
    const parents = new Set<Node>();
    markers.forEach((span) => {
      const parent = span.parentNode;
      if (!parent) return;
      parent.replaceChild(document.createTextNode(span.dataset.avOrig ?? span.textContent ?? ""), span);
      parents.add(parent);
    });
    // Merge the text nodes we split earlier back into clean runs.
    parents.forEach((p) => (p as Element).normalize?.());
  });
  processed = new WeakSet<Text>();
  sessionCache = new Map();
}

function withObserverPaused(fn: () => void): void {
  observer?.disconnect();
  try {
    fn();
  } finally {
    if (enabled && observer) observer.observe(document.body, { childList: true, subtree: true });
  }
}
