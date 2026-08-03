/**
 * cimeter.ts — actionable Reading Coach.
 *
 * When enabled, samples the page's text once (not continuously, unlike
 * immersion.ts) and shows a small floating badge reporting the % of
 * vocabulary the learner already knows, an overall CEFR estimate, and an
 * i+1 verdict — so they can judge whether a page is worth reading before
 * committing to it.
 */
import {
  analyzeReadingCoach,
  prepareReadingCoach,
  type ReadingCoachResult,
} from "../shared/api";
import { sampleText } from "./page-text";

export interface CiMeterDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
}

const SAMPLE_CHAR_BUDGET = 6000;

let deps: CiMeterDeps;
let enabled = false;
let badge: HTMLElement | null = null;
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
    void runScan();
  } else {
    removeBadge();
    lastText = "";
  }
}

// ---------------------------------------------------------------------------
// Scan / analyze
// ---------------------------------------------------------------------------

async function runScan(): Promise<void> {
  if (!enabled) return;
  const username = await deps.getUsername().catch(() => null);
  if (!username || !enabled) return;

  const text = sampleText(SAMPLE_CHAR_BUDGET);
  if (!text) return;
  lastText = text;

  renderBadge(null, true);
  try {
    const result = await analyzeReadingCoach(text);
    if (!enabled) return;
    renderBadge(result, false);
  } catch (err) {
    console.debug("[cimeter] scan failed:", err);
    if (enabled) renderBadge(null, false);
  }
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

function verdictIcon(verdict: ReadingCoachResult["verdict"]): string {
  switch (verdict) {
    case "ideal": return "🟢";
    case "close": return "🟡";
    case "too_easy": return "🔵";
    case "too_hard": return "🔴";
    default: return "⚪";
  }
}

function verdictText(t: CiMeterDeps["t"], verdict: ReadingCoachResult["verdict"]): string {
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

function renderBadge(result: ReadingCoachResult | null, loading: boolean): void {
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
  const projection = document.createElement("div");
  projection.className = "veksha-reading-projection";
  projection.textContent = t(
    "reading_coach_projection",
    "Learn these words: {before}% → {after}% coverage",
  )
    .replace("{before}", String(pct))
    .replace("{after}", String(Math.round(result.projected_known_pct * 100)));
  detail.append(verdict, projection);

  const selectable: string[] = [];
  if (result.obstacles.length) {
    const title = document.createElement("strong");
    title.className = "veksha-reading-title";
    title.textContent = t("reading_coach_obstacles", "Words blocking this page");
    const list = document.createElement("div");
    list.className = "veksha-reading-list";
    for (const obstacle of result.obstacles) {
      const row = document.createElement("label");
      row.className = "veksha-reading-word";
      const canPrepare = obstacle.knowledge === "unseen";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = canPrepare;
      checkbox.disabled = !canPrepare;
      if (canPrepare) selectable.push(obstacle.term);
      const word = document.createElement("span");
      word.innerHTML = `<b>${escapeHtml(obstacle.term)}</b><small>${obstacle.cefr} · ${obstacle.occurrences}×</small>`;
      const state = document.createElement("em");
      state.textContent = obstacle.knowledge === "learning"
        ? t("reading_coach_learning", "learning")
        : obstacle.knowledge === "suggested"
          ? t("reading_coach_inbox", "in inbox")
          : "";
      row.append(checkbox, word, state);
      list.appendChild(row);
    }
    detail.append(title, list);

    if (selectable.length) {
      const prepareBtn = document.createElement("button");
      prepareBtn.type = "button";
      prepareBtn.className = "veksha-ci-badge-refine";
      prepareBtn.textContent = t("reading_coach_prepare", "Prepare selected words");
      prepareBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        const selected = Array.from(
          list.querySelectorAll<HTMLInputElement>('input[type="checkbox"]:checked'),
        ).map((input) => input.parentElement?.querySelector("b")?.textContent ?? "").filter(Boolean);
        if (!selected.length) return;
        prepareBtn.disabled = true;
        prepareBtn.textContent = t("reading_coach_preparing", "Preparing…");
        void prepareReadingCoach(lastText, selected, location.href)
          .then((prepared) => {
            prepareBtn.textContent = t(
              "reading_coach_added",
              "{n} word(s) added to your Inbox",
            ).replace("{n}", String(prepared.added));
            window.setTimeout(() => void runScan(), 1200);
          })
          .catch(() => {
            prepareBtn.disabled = false;
            prepareBtn.textContent = t("reading_coach_failed", "Could not prepare words");
          });
      });
      detail.appendChild(prepareBtn);
    }
  } else {
    const ready = document.createElement("div");
    ready.className = "veksha-reading-ready";
    ready.textContent = t("reading_coach_ready", "No high-impact blockers found. Start reading!");
    detail.appendChild(ready);
  }
  badge.replaceChildren(pill, detail);

  pill.addEventListener("click", () => {
    detail.hidden = !detail.hidden;
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
