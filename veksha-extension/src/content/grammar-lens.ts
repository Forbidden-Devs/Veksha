/** Grammar Lens — inline, reversible grammatical-role highlighting. */
import {
  analyzeGrammarLens,
  getGrammarMemory,
  setGrammarMemoryStatus,
  type GrammarBlockAnalysis,
  type GrammarMemoryItem,
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
let observer: MutationObserver | null = null;
let scanTimer: ReturnType<typeof setTimeout> | null = null;
let legend: HTMLElement | null = null;
let expanded = false;
let lastAnalysis: { text: string; analysis: GrammarBlockAnalysis } | null = null;
let analysisLoading = false;
let analysisError: string | null = null;
let analysisSequence = 0;
let memoryItems: GrammarMemoryItem[] = [];
let memoryLoading = false;

export function initGrammarLens(value: GrammarLensDeps): void {
  deps = value;
}

export function isGrammarLensEnabled(): boolean {
  return enabled;
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
    void refreshGrammarMemory();
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
    expanded = false;
    lastAnalysis = null;
    analysisLoading = false;
    analysisError = null;
    analysisSequence += 1;
    memoryItems = [];
    memoryLoading = false;
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
      const response = await analyzeGrammarLens(
        pending.map((item) => item.text),
        location.href,
      );
      if (!enabled || scanGeneration !== generation) return;
      response.blocks.forEach((block, index) => {
        const source = pending[index];
        if (!source) return;
        sessionCache.set(source.text, block);
        ready.push({ node: source.node, analysis: block });
      });
      void refreshGrammarMemory();
    }

    if (!enabled || scanGeneration !== generation) return;
    withObserverPaused(() => ready.forEach(({ node, analysis }) => applyToNode(node, analysis)));
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

function applyToNode(node: Text, analysis: GrammarBlockAnalysis): void {
  const { segments, annotations = [] } = analysis;
  if (!node.isConnected || !node.parentNode || (!segments.length && !annotations.length)) return;
  const original = node.data;
  const annotationRanges = annotations.flatMap((annotation) => {
    const start = original.indexOf(annotation.text);
    return start < 0 ? [] : [{ annotation, start, end: start + annotation.text.length }];
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
    if (matchingInsights.length) marker.classList.add("av-grammar-has-insight");
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
    title.textContent = deps.t("grammar_memory_title", "Grammar Memory");
    const buttons = document.createElement("div");
    buttons.className = "veksha-grammar-legend-buttons";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "veksha-grammar-legend-toggle";
    toggle.addEventListener("click", () => {
      if (!expanded && !lastAnalysis && !analysisLoading && !analysisError) return;
      expanded = !expanded;
      syncLegendMode();
    });
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "×";
    close.title = deps.t("grammar_memory_disable", "Turn off Grammar Memory");
    close.addEventListener("click", () => {
      void chrome.storage.local.set({ [CONFIG.STORAGE_KEY_GRAMMAR_LENS]: false });
      setGrammarLensEnabled(false);
    });
    buttons.append(toggle, close);
    header.append(title, buttons);

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
    const hint = document.createElement("div");
    hint.className = "veksha-grammar-legend-hint";
    hint.textContent = deps.t(
      "grammar_hint_select",
      "Select a sentence on the page and press the 🔍 button next to it for a detailed grammar analysis.",
    );
    const detail = document.createElement("section");
    detail.className = "veksha-grammar-detail";
    detail.hidden = true;
    const status = document.createElement("div");
    status.className = "veksha-grammar-legend-status";
    legend.append(header, items, hint, detail, status);
    document.body.appendChild(legend);
    syncLegendMode();
  }
  const status = legend.querySelector<HTMLElement>(".veksha-grammar-legend-status");
  if (status) {
    status.textContent = loading ? deps.t("grammar_memory_scanning", "Analyzing visible text…") : "";
    status.hidden = !loading;
  }
}

/** Reflect the expanded/collapsed state in the legend DOM. */
function syncLegendMode(): void {
  if (!legend) return;
  const detail = legend.querySelector<HTMLElement>(".veksha-grammar-detail");
  const hint = legend.querySelector<HTMLElement>(".veksha-grammar-legend-hint");
  const toggle = legend.querySelector<HTMLButtonElement>(".veksha-grammar-legend-toggle");
  const hasContent = Boolean(lastAnalysis) || memoryItems.length > 0 || memoryLoading
    || analysisLoading || Boolean(analysisError);
  if (!hasContent) expanded = false;
  if (detail) detail.hidden = !expanded;
  if (hint) hint.hidden = expanded;
  if (toggle) {
    toggle.textContent = expanded ? "–" : "+";
    toggle.disabled = !expanded && !hasContent;
    toggle.title = expanded
      ? deps.t("grammar_memory_collapse", "Collapse the analysis")
      : deps.t("grammar_memory_expand", "Show grammar memory");
  }
}

function renderDetail(): void {
  const detail = legend?.querySelector<HTMLElement>(".veksha-grammar-detail");
  if (!detail) return;
  detail.replaceChildren();

  if (analysisError) {
    const error = document.createElement("div");
    error.className = "veksha-grammar-detail-error";
    error.textContent = analysisError;
    detail.appendChild(error);
    syncLegendMode();
    return;
  }
  if (analysisLoading) {
    const loading = document.createElement("div");
    loading.className = "veksha-grammar-detail-loading";
    loading.textContent = deps.t("grammar_analysis_loading", "Analyzing the sentence…");
    detail.appendChild(loading);
    syncLegendMode();
    return;
  }
  const body = document.createElement("div");
  body.className = "veksha-grammar-detail-body";
  if (lastAnalysis) {
    const quote = document.createElement("q");
    quote.className = "veksha-grammar-detail-quote";
    quote.textContent = lastAnalysis.text;
    detail.appendChild(quote);
  }
  const { segments, annotations } = lastAnalysis?.analysis ?? { segments: [], annotations: [] };

  if (segments.length) {
    const rolesTitle = document.createElement("strong");
    rolesTitle.textContent = deps.t("grammar_roles_title", "Sentence roles");
    body.appendChild(rolesTitle);
    for (const segment of segments) {
      const row = document.createElement("div");
      row.className = "veksha-grammar-detail-seg";
      const dot = document.createElement("i");
      dot.dataset.role = segment.role;
      const copy = document.createElement("span");
      const label = document.createElement("b");
      label.textContent = roleLabel(segment.role);
      copy.append(label, document.createTextNode(` — ${segment.text}`));
      row.append(dot, copy);
      if (segment.explanation) {
        const explanation = document.createElement("small");
        explanation.textContent = segment.explanation;
        row.appendChild(explanation);
      }
      body.appendChild(row);
    }
  }

  if (annotations.length) {
    const patternsTitle = document.createElement("strong");
    patternsTitle.textContent = deps.t("grammar_patterns_title", "Grammar in context");
    body.appendChild(patternsTitle);
    for (const annotation of annotations) {
      const card = document.createElement("div");
      card.className = "veksha-grammar-insight";
      card.dataset.category = annotation.category;
      const label = document.createElement("b");
      label.textContent = annotation.label;
      const cardQuote = document.createElement("q");
      cardQuote.textContent = annotation.text.trim();
      card.append(label, cardQuote);
      if (annotation.explanation) {
        const explanation = document.createElement("span");
        explanation.textContent = annotation.explanation;
        card.appendChild(explanation);
      }
      body.appendChild(card);
    }
  }

  if (lastAnalysis && !segments.length && !annotations.length) {
    const empty = document.createElement("div");
    empty.className = "veksha-grammar-detail-loading";
    empty.textContent = deps.t("grammar_analysis_empty", "No notable grammar found in this selection.");
    body.appendChild(empty);
  }

  renderMemory(body);

  detail.appendChild(body);
  syncLegendMode();
}

/** Detailed analysis of a user-selected sentence, shown in the legend panel. */
export function analyzeGrammarSelection(rawText: string): void {
  if (!enabled) return;
  const text = rawText.trim().slice(0, 1000);
  if (!text) return;
  renderLegend(false);
  const sequence = ++analysisSequence;
  expanded = true;
  analysisLoading = true;
  analysisError = null;
  renderDetail();

  void (async () => {
    try {
      const username = await deps.getUsername().catch(() => null);
      if (sequence !== analysisSequence) return;
      if (!username) {
        analysisLoading = false;
        analysisError = deps.t("content_no_user", "Open the Veksha popup and enter your name first.");
        renderDetail();
        return;
      }
      let analysis = sessionCache.get(text) ?? null;
      if (!analysis) {
        const response = await analyzeGrammarLens([text], location.href);
        analysis = response.blocks[0] ?? { segments: [], annotations: [] };
        sessionCache.set(text, analysis);
      }
      if (sequence !== analysisSequence) return;
      analysisLoading = false;
      lastAnalysis = { text, analysis };
      void refreshGrammarMemory();
      renderDetail();
    } catch (error) {
      console.debug("[grammar-lens] selection analysis failed:", error);
      if (sequence !== analysisSequence) return;
      analysisLoading = false;
      analysisError = deps.t("grammar_analysis_failed", "Could not analyze the selection. Try again.");
      renderDetail();
    }
  })();
}

async function refreshGrammarMemory(): Promise<void> {
  if (!enabled || memoryLoading) return;
  memoryLoading = true;
  renderDetail();
  try {
    const response = await getGrammarMemory();
    if (!enabled) return;
    memoryItems = response.items;
  } catch (error) {
    console.debug("[grammar-memory] load failed:", error);
  } finally {
    memoryLoading = false;
    if (enabled) renderDetail();
  }
}

function renderMemory(body: HTMLElement): void {
  const title = document.createElement("strong");
  title.textContent = deps.t("grammar_memory_patterns", "Your grammar memory");
  body.appendChild(title);
  if (memoryLoading && !memoryItems.length) {
    const loading = document.createElement("div");
    loading.className = "veksha-grammar-detail-loading";
    loading.textContent = deps.t("grammar_memory_loading", "Loading saved patterns…");
    body.appendChild(loading);
    return;
  }
  if (!memoryItems.length) {
    const empty = document.createElement("div");
    empty.className = "veksha-grammar-detail-loading";
    empty.textContent = deps.t(
      "grammar_memory_empty",
      "Patterns found while you read will collect here.",
    );
    body.appendChild(empty);
    return;
  }
  for (const item of memoryItems.slice(0, 8)) {
    const card = document.createElement("article");
    card.className = "veksha-grammar-memory-card";
    if (item.status === "mastered") card.classList.add("is-mastered");
    const heading = document.createElement("div");
    const label = document.createElement("b");
    label.textContent = item.label;
    const count = document.createElement("small");
    count.textContent = deps.t("grammar_memory_seen", "Seen {n}×")
      .replace("{n}", String(item.seen_count));
    heading.append(label, count);
    card.appendChild(heading);
    if (item.explanation) {
      const explanation = document.createElement("span");
      explanation.textContent = item.explanation;
      card.appendChild(explanation);
    }
    const example = item.encounters[0]?.example;
    if (example) {
      const quote = document.createElement("q");
      quote.textContent = example;
      card.appendChild(quote);
    }
    const status = document.createElement("button");
    status.type = "button";
    status.textContent = item.status === "mastered"
      ? deps.t("grammar_memory_reopen", "Study again")
      : deps.t("grammar_memory_mastered", "Mark as mastered");
    status.addEventListener("click", (event) => {
      event.stopPropagation();
      status.disabled = true;
      const next = item.status === "mastered" ? "learning" : "mastered";
      void setGrammarMemoryStatus(item.item_id, next)
        .then((updated) => {
          memoryItems = memoryItems.map((candidate) => (
            candidate.item_id === updated.item_id ? updated : candidate
          ));
          renderDetail();
        })
        .catch(() => {
          status.disabled = false;
        });
    });
    card.appendChild(status);
    body.appendChild(card);
  }
}
