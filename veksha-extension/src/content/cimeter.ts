/**
 * cimeter.ts — Comprehensible Input Meter.
 *
 * When enabled, samples the page's text once (not continuously, unlike
 * immersion.ts) and shows a small floating badge reporting the % of
 * vocabulary the learner already knows, an overall CEFR estimate, and an
 * i+1 verdict — so they can judge whether a page is worth reading before
 * committing to it.
 */
import { analyzeCiMeter, type CiMeterResult } from "../shared/api";
import { sampleText } from "./page-text";

export interface CiMeterDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
}

const SAMPLE_CHAR_BUDGET = 6000;

let deps: CiMeterDeps;
let enabled = false;
let badge: HTMLElement | null = null;
let lastResult: CiMeterResult | null = null;
let lastText = "";

export function initCiMeter(d: CiMeterDeps): void {
  deps = d;
}

export function isCiMeterEnabled(): boolean {
  return enabled;
}

export function setCiMeterEnabled(on: boolean): void {
  if (on === enabled) return;
  enabled = on;
  if (on) {
    void runScan(false);
  } else {
    removeBadge();
    lastResult = null;
    lastText = "";
  }
}

// ---------------------------------------------------------------------------
// Scan / analyze
// ---------------------------------------------------------------------------

async function runScan(refine: boolean): Promise<void> {
  if (!enabled) return;
  const username = await deps.getUsername().catch(() => null);
  if (!username || !enabled) return;

  const text = refine && lastText ? lastText : sampleText(SAMPLE_CHAR_BUDGET);
  if (!text) return;
  lastText = text;

  renderBadge(null, true);
  try {
    const result = await analyzeCiMeter(text, refine);
    if (!enabled) return;
    lastResult = result;
    renderBadge(result, false);
  } catch (err) {
    console.debug("[cimeter] scan failed:", err);
    if (enabled) renderBadge(null, false);
  }
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

function verdictIcon(verdict: CiMeterResult["verdict"]): string {
  switch (verdict) {
    case "ideal": return "🟢";
    case "close": return "🟡";
    case "too_easy": return "🔵";
    case "too_hard": return "🔴";
    default: return "⚪";
  }
}

function verdictText(t: CiMeterDeps["t"], verdict: CiMeterResult["verdict"]): string {
  switch (verdict) {
    case "ideal": return t("ci_meter_verdict_ideal", "Great i+1 content for you — mostly familiar with a healthy stretch of new words.");
    case "too_easy": return t("ci_meter_verdict_too_easy", "You know this well already — good for fluency practice, but little new vocabulary.");
    case "too_hard": return t("ci_meter_verdict_too_hard", "This may be too difficult right now — expect to look up a lot of words.");
    default: return t("ci_meter_verdict_close", "Close to your level.");
  }
}

function removeBadge(): void {
  badge?.remove();
  badge = null;
}

function renderBadge(result: CiMeterResult | null, loading: boolean): void {
  const { t } = deps;
  if (!badge) {
    badge = document.createElement("div");
    badge.className = "veksha-ci-badge";
    badge.dataset.avSkip = "1";
    document.body.appendChild(badge);
  }

  if (loading) {
    const loadingPill = document.createElement("div");
    loadingPill.className = "veksha-ci-badge-pill";
    loadingPill.textContent = t("ci_meter_loading", "Checking readability…");
    badge.replaceChildren(loadingPill);
    return;
  }
  if (!result) {
    removeBadge();
    return;
  }

  const pct = Math.round(result.known_pct * 100);
  const icon = verdictIcon(result.verdict);
  const summary = t("ci_meter_badge_known", "{pct}% known · {cefr}")
    .replace("{pct}", String(pct))
    .replace("{cefr}", result.cefr);

  const pill = document.createElement("button");
  pill.type = "button";
  pill.className = "veksha-ci-badge-pill";
  pill.textContent = `${icon} ${summary}`;

  const detail = document.createElement("div");
  detail.className = "veksha-ci-badge-detail";
  detail.hidden = true;
  const verdict = document.createElement("div");
  verdict.className = "veksha-ci-badge-verdict";
  verdict.textContent = verdictText(t, result.verdict);
  const refineBtn = document.createElement("button");
  refineBtn.type = "button";
  refineBtn.className = "veksha-ci-badge-refine";
  refineBtn.textContent = t("ci_meter_refine", "Refine with AI");
  detail.append(verdict, refineBtn);
  badge.replaceChildren(pill, detail);

  pill.addEventListener("click", () => {
    detail.hidden = !detail.hidden;
  });
  refineBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    void runScan(true);
  });
}
