/** Grammar Lens — inline, reversible grammatical-role highlighting. */
import {
  analyzeGrammarLens,
  type GrammarAnnotation,
  type GrammarBlockAnalysis,
  type GrammarRole,
  type GrammarSegment,
} from "../shared/api";
import { CONFIG } from "../shared/config";
import { isVisible, SKIP_CLOSEST, SKIP_TAGS } from "./page-text";

export interface GrammarLensDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
}

const MIN_CHARS = 18;
const BATCH = 18;
const VIEWPORT_MARGIN = 500;
const DEBOUNCE_MS = 350;
const ROLES: GrammarRole[] = ["subject", "verb", "object", "place", "time", "modifier"];

const ROLE_FALLBACKS: Record<GrammarRole, string> = {
  subject: "Subject",
  verb: "Verb",
  object: "Object",
  place: "Place",
  time: "Time",
  modifier: "Modifier",
};

let deps: GrammarLensDeps;
let enabled = false;
let scanning = false;
let generation = 0;
let processed = new WeakSet<Text>();
let sessionCache = new Map<string, GrammarBlockAnalysis>();
let visibleInsights = new Map<string, GrammarAnnotation>();
let insightIds = new Map<string, string>();
let insightSequence = 0;
let observer: MutationObserver | null = null;
let scanTimer: ReturnType<typeof setTimeout> | null = null;
let legend: HTMLElement | null = null;

export function initGrammarLens(value: GrammarLensDeps): void {
  deps = value;
}

export function setGrammarLensEnabled(on: boolean): void {
  if (on === enabled) return;
  enabled = on;
  generation += 1;
  if (on) {
    renderLegend(true);
    window.addEventListener("scroll", scheduleScan, { passive: true });
    window.addEventListener("resize", scheduleScan, { passive: true });
    observer = new MutationObserver(scheduleScan);
    observer.observe(document.body, { childList: true, subtree: true });
    scheduleScan();
  } else {
    window.removeEventListener("scroll", scheduleScan);
    window.removeEventListener("resize", scheduleScan);
    observer?.disconnect();
    observer = null;
    if (scanTimer) clearTimeout(scanTimer);
    scanTimer = null;
    restoreAll();
    legend?.remove();
    legend = null;
  }
}

function scheduleScan(): void {
  if (!enabled) return;
  if (scanTimer) clearTimeout(scanTimer);
  scanTimer = setTimeout(() => {
    scanTimer = null;
    void scan();
  }, DEBOUNCE_MS);
}

function isAnalyzable(value: string): boolean {
  const text = value.trim();
  return text.length >= MIN_CHARS && /\p{L}/u.test(text) && /\s/.test(text);
}

function collectNodes(limit: number): Text[] {
  const nodes: Text[] = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node: Node): number {
      const text = node as Text;
      const parent = text.parentElement;
      if (processed.has(text) || !parent) return NodeFilter.FILTER_REJECT;
      if (SKIP_TAGS.has(parent.tagName) || parent.isContentEditable) return NodeFilter.FILTER_REJECT;
      if (parent.closest(SKIP_CLOSEST)) return NodeFilter.FILTER_REJECT;
      if (!isAnalyzable(text.data) || !isVisible(parent, VIEWPORT_MARGIN)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (nodes.length < limit && walker.nextNode()) nodes.push(walker.currentNode as Text);
  return nodes;
}

async function scan(): Promise<void> {
  if (!enabled || scanning) return;
  const nodes = collectNodes(BATCH);
  if (!nodes.length) {
    renderLegend(false);
    return;
  }

  renderLegend(true);
  const username = await deps.getUsername().catch(() => null);
  if (!username || !enabled) {
    if (enabled) renderLegend(false);
    return;
  }
  const scanGeneration = generation;
  scanning = true;
  nodes.forEach((node) => processed.add(node));

  try {
    const pending: { node: Text; text: string }[] = [];
    const ready: { node: Text; analysis: GrammarBlockAnalysis }[] = [];
    for (const node of nodes) {
      const cached = sessionCache.get(node.data);
      if (cached) ready.push({ node, analysis: cached });
      else pending.push({ node, text: node.data });
    }

    if (pending.length) {
      const response = await analyzeGrammarLens(pending.map((item) => item.text));
      if (!enabled || scanGeneration !== generation) return;
      response.blocks.forEach((block, index) => {
        const source = pending[index];
        if (!source) return;
        sessionCache.set(source.text, block);
        ready.push({ node: source.node, analysis: block });
      });
    }

    if (!enabled || scanGeneration !== generation) return;
    withObserverPaused(() => ready.forEach(({ node, analysis }) => applyToNode(node, analysis)));
    renderGrammarInsights();
    renderLegend(false);
  } catch (error) {
    console.debug("[grammar-lens] scan failed:", error);
    if (enabled) renderLegend(false);
  } finally {
    scanning = false;
    if (enabled && collectNodes(1).length) scheduleScan();
  }
}

function roleLabel(role: GrammarRole): string {
  return deps.t(`grammar_role_${role}`, ROLE_FALLBACKS[role]);
}

function makeMarker(segment: GrammarSegment, insightLabels: string[]): HTMLElement {
  const marker = document.createElement("span");
  marker.className = "av-grammar";
  marker.dataset.avGrammarRole = segment.role;
  marker.dataset.avOrig = segment.text;
  marker.textContent = segment.text;
  const roleTitle = segment.explanation
    ? `${roleLabel(segment.role)} — ${segment.explanation}`
    : roleLabel(segment.role);
  marker.title = insightLabels.length ? `${roleTitle}\n${insightLabels.join(" · ")}` : roleTitle;
  return marker;
}

function insightKey(annotation: GrammarAnnotation): string {
  return `${annotation.category}\u0000${annotation.label}\u0000${annotation.text}`;
}

function registerInsight(annotation: GrammarAnnotation): string {
  const key = insightKey(annotation);
  let id = insightIds.get(key);
  if (!id) {
    id = `avgi-${++insightSequence}`;
    insightIds.set(key, id);
  }
  visibleInsights.delete(key);
  visibleInsights.set(key, annotation);
  while (visibleInsights.size > 12) visibleInsights.delete(visibleInsights.keys().next().value!);
  return id;
}

function applyToNode(node: Text, analysis: GrammarBlockAnalysis): void {
  const { segments, annotations = [] } = analysis;
  if (!node.isConnected || !node.parentNode || (!segments.length && !annotations.length)) return;
  const original = node.data;
  const annotationRanges = annotations.flatMap((annotation) => {
    const start = original.indexOf(annotation.text);
    return start < 0 ? [] : [{ annotation, start, end: start + annotation.text.length, id: registerInsight(annotation) }];
  });
  const fragment = document.createDocumentFragment();
  let cursor = 0;
  let changed = false;

  for (const segment of segments) {
    const index = original.indexOf(segment.text, cursor);
    if (index < 0) continue;
    if (index > cursor) fragment.appendChild(document.createTextNode(original.slice(cursor, index)));
    const end = index + segment.text.length;
    const matchingInsights = annotationRanges.filter((item) => index < item.end && end > item.start);
    const marker = makeMarker(segment, matchingInsights.map((item) => item.annotation.label));
    if (matchingInsights.length) {
      marker.classList.add("av-grammar-has-insight");
      marker.dataset.avGrammarAnnotation = matchingInsights.map((item) => item.id).join(" ");
    }
    fragment.appendChild(marker);
    cursor = end;
    changed = true;
  }
  if (!changed) return;
  if (cursor < original.length) fragment.appendChild(document.createTextNode(original.slice(cursor)));
  fragment.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) processed.add(child as Text);
  });
  node.parentNode.replaceChild(fragment, node);
}

function restoreAll(): void {
  withObserverPaused(() => {
    const parents = new Set<Node>();
    document.querySelectorAll<HTMLElement>(".av-grammar").forEach((marker) => {
      const parent = marker.parentNode;
      if (!parent) return;
      parent.replaceChild(document.createTextNode(marker.dataset.avOrig ?? marker.textContent ?? ""), marker);
      parents.add(parent);
    });
    parents.forEach((parent) => (parent as Element).normalize?.());
  });
  processed = new WeakSet<Text>();
  sessionCache = new Map();
  visibleInsights = new Map();
  insightIds = new Map();
  insightSequence = 0;
}

function withObserverPaused(fn: () => void): void {
  observer?.disconnect();
  try {
    fn();
  } finally {
    if (enabled && observer) observer.observe(document.body, { childList: true, subtree: true });
  }
}

function renderLegend(loading: boolean): void {
  if (!legend) {
    legend = document.createElement("aside");
    legend.className = "veksha-grammar-legend";
    legend.dataset.avSkip = "1";

    const header = document.createElement("div");
    header.className = "veksha-grammar-legend-header";
    const title = document.createElement("strong");
    title.textContent = deps.t("grammar_lens_title", "Grammar Lens");
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "×";
    close.title = deps.t("grammar_lens_disable", "Turn off Grammar Lens");
    close.addEventListener("click", () => {
      void chrome.storage.local.set({ [CONFIG.STORAGE_KEY_GRAMMAR_LENS]: false });
      setGrammarLensEnabled(false);
    });
    header.append(title, close);

    const items = document.createElement("div");
    items.className = "veksha-grammar-legend-items";
    for (const role of ROLES) {
      const item = document.createElement("span");
      item.className = "veksha-grammar-legend-item";
      const dot = document.createElement("i");
      dot.dataset.role = role;
      item.append(dot, document.createTextNode(roleLabel(role)));
      items.appendChild(item);
    }
    const status = document.createElement("div");
    status.className = "veksha-grammar-legend-status";
    const insights = document.createElement("section");
    insights.className = "veksha-grammar-insights";
    insights.hidden = true;
    const insightsTitle = document.createElement("strong");
    insightsTitle.textContent = deps.t("grammar_patterns_title", "Grammar in context");
    const insightsList = document.createElement("div");
    insightsList.className = "veksha-grammar-insights-list";
    insights.append(insightsTitle, insightsList);
    legend.append(header, items, insights, status);
    document.body.appendChild(legend);
    renderGrammarInsights();
  }
  const status = legend.querySelector<HTMLElement>(".veksha-grammar-legend-status");
  if (status) {
    status.textContent = loading ? deps.t("grammar_lens_loading", "Analyzing visible text…") : "";
    status.hidden = !loading;
  }
}

function focusInsight(id: string, focused: boolean): void {
  document.querySelectorAll<HTMLElement>(".av-grammar[data-av-grammar-annotation]").forEach((marker) => {
    const ids = marker.dataset.avGrammarAnnotation?.split(" ") ?? [];
    if (ids.includes(id)) marker.classList.toggle("av-grammar-focus", focused);
  });
}

function renderGrammarInsights(): void {
  if (!legend) return;
  const section = legend.querySelector<HTMLElement>(".veksha-grammar-insights");
  const list = legend.querySelector<HTMLElement>(".veksha-grammar-insights-list");
  if (!section || !list) return;
  list.replaceChildren();
  const entries = [...visibleInsights.entries()].slice(-8).reverse();
  section.hidden = entries.length === 0;
  for (const [key, annotation] of entries) {
    const id = insightIds.get(key);
    if (!id) continue;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "veksha-grammar-insight";
    card.dataset.category = annotation.category;
    const label = document.createElement("b");
    label.textContent = annotation.label;
    const quote = document.createElement("q");
    quote.textContent = annotation.text.trim();
    card.append(label, quote);
    if (annotation.explanation) {
      const explanation = document.createElement("span");
      explanation.textContent = annotation.explanation;
      card.appendChild(explanation);
    }
    card.addEventListener("mouseenter", () => focusInsight(id, true));
    card.addEventListener("mouseleave", () => focusInsight(id, false));
    card.addEventListener("focus", () => focusInsight(id, true));
    card.addEventListener("blur", () => focusInsight(id, false));
    list.appendChild(card);
  }
}
