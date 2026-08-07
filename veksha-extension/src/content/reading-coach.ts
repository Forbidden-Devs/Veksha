/**
 * reading-coach.ts — actionable page-reading guidance.
 *
 * When enabled, samples the page's text once and shows a small floating badge reporting the % of
 * vocabulary the learner already knows, an overall CEFR estimate, and an
 * i+1 verdict — so they can judge whether a page is worth reading before
 * committing to it.
 */
import {
  analyzeReadingCoach,
  checkReadingAnswer,
  createReadingQuestion,
  helpReadingParagraph,
  prepareReadingCoach,
  type ReadingCoachResult,
} from "../shared/api";
import { sampleText } from "./page-text";

export interface ReadingCoachDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
}

const SAMPLE_CHAR_BUDGET = 6000;

let deps: ReadingCoachDeps;
let enabled = false;
let badge: HTMLElement | null = null;
let lastText = "";

export function initReadingCoach(d: ReadingCoachDeps): void {
  deps = d;
}

export function isReadingCoachEnabled(): boolean {
  return enabled;
}

export function setReadingCoachEnabled(on: boolean): void {
  if (on === enabled) return;
  enabled = on;
  if (on) {
    void runScan();
  } else {
    removeBadge();
    lastText = "";
  }
}

export function refreshReadingCoach(): void {
  if (enabled) void runScan();
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
    console.debug("[reading-coach] scan failed:", err);
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

function verdictText(t: ReadingCoachDeps["t"], verdict: ReadingCoachResult["verdict"]): string {
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

  const structure = document.createElement("div");
  structure.className = "veksha-reading-structure";
  structure.textContent = t(
    "reading_coach_structure",
    "Vocabulary {lexical} · sentence structure {structure} · {average} words/sentence",
  )
    .replace("{lexical}", result.lexical_cefr)
    .replace("{structure}", result.structure_cefr)
    .replace("{average}", String(result.average_sentence_words));
  detail.appendChild(structure);

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
  detail.appendChild(renderStudyTools(t));
  badge.replaceChildren(pill, detail);

  pill.addEventListener("click", () => {
    detail.hidden = !detail.hidden;
  });
}

function selectedPassage(): string {
  return (window.getSelection()?.toString() ?? "").replace(/\s+/g, " ").trim().slice(0, 3000);
}

function renderStudyTools(t: ReadingCoachDeps["t"]): HTMLElement {
  const section = document.createElement("section");
  section.className = "veksha-reading-tools";
  const heading = document.createElement("strong");
  heading.textContent = t("reading_coach_selected_title", "Selected paragraph");
  const hint = document.createElement("p");
  hint.textContent = t(
    "reading_coach_selected_hint",
    "Select a paragraph on the page, then ask for a hint or check your understanding.",
  );
  const actions = document.createElement("div");
  actions.className = "veksha-reading-tool-actions";
  const helpButton = document.createElement("button");
  helpButton.type = "button";
  helpButton.textContent = t("reading_coach_help_paragraph", "Help me understand");
  const questionButton = document.createElement("button");
  questionButton.type = "button";
  questionButton.textContent = t("reading_coach_check_understanding", "Check understanding");
  const output = document.createElement("div");
  output.className = "veksha-reading-tool-output";
  actions.append(helpButton, questionButton);
  section.append(heading, hint, actions, output);

  helpButton.addEventListener("click", async () => {
    const passage = selectedPassage();
    if (passage.length < 20) {
      output.textContent = t("reading_coach_select_paragraph", "Select a complete paragraph first.");
      return;
    }
    helpButton.disabled = true;
    output.textContent = t("reading_coach_working", "Preparing a reading hint…");
    try {
      const result = await helpReadingParagraph(passage);
      const original = document.createElement("p");
      original.className = "veksha-reading-original";
      original.textContent = result.original;
      const explanation = document.createElement("p");
      explanation.textContent = result.explanation;
      const reveal = document.createElement("button");
      reveal.type = "button";
      reveal.textContent = t("reading_coach_reveal_translation", "Reveal translation");
      const translation = document.createElement("p");
      translation.className = "veksha-reading-translation";
      translation.textContent = result.translation;
      translation.hidden = true;
      reveal.addEventListener("click", () => {
        translation.hidden = !translation.hidden;
        reveal.textContent = translation.hidden
          ? t("reading_coach_reveal_translation", "Reveal translation")
          : t("reading_coach_hide_translation", "Hide translation");
      });
      output.replaceChildren(original, explanation, reveal, translation);
    } catch {
      output.textContent = t(
        "reading_coach_advanced_unavailable",
        "This advanced Reading Coach tool requires activation or is temporarily unavailable.",
      );
    } finally {
      helpButton.disabled = false;
    }
  });

  questionButton.addEventListener("click", async () => {
    const passage = selectedPassage();
    if (passage.length < 40) {
      output.textContent = t("reading_coach_select_paragraph", "Select a complete paragraph first.");
      return;
    }
    questionButton.disabled = true;
    output.textContent = t("reading_coach_working", "Preparing a reading question…");
    try {
      const generated = await createReadingQuestion(passage);
      const question = document.createElement("p");
      question.className = "veksha-reading-question";
      question.textContent = generated.question;
      const answer = document.createElement("textarea");
      answer.rows = 3;
      answer.maxLength = 2000;
      answer.placeholder = t("reading_coach_answer_placeholder", "Answer in your own words");
      const check = document.createElement("button");
      check.type = "button";
      check.textContent = t("reading_coach_check_answer", "Check answer");
      const feedback = document.createElement("p");
      check.addEventListener("click", async () => {
        if (!answer.value.trim()) return;
        check.disabled = true;
        feedback.textContent = t("reading_coach_working", "Checking…");
        try {
          const checked = await checkReadingAnswer(generated.question_id, answer.value);
          feedback.dataset.outcome = checked.outcome;
          feedback.textContent = checked.feedback;
        } catch {
          feedback.textContent = t("reading_coach_question_expired", "This question expired. Create a new one.");
        } finally {
          check.disabled = false;
        }
      });
      output.replaceChildren(question, answer, check, feedback);
    } catch {
      output.textContent = t(
        "reading_coach_advanced_unavailable",
        "This advanced Reading Coach tool requires activation or is temporarily unavailable.",
      );
    } finally {
      questionButton.disabled = false;
    }
  });
  return section;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
