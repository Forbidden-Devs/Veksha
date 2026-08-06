/** Pattern Workshop opens only from a learner-selected sentence. */
import {
  analyzePatternWorkshop,
  completePatternWorkshop,
  type PatternWorkshopDraft,
} from "../shared/api";

export interface PatternWorkshopDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
}

let deps: PatternWorkshopDeps;
let panel: HTMLElement | null = null;

export function initPatternWorkshop(value: PatternWorkshopDeps): void {
  deps = value;
}

export function closePatternWorkshop(): void {
  panel?.remove();
  panel = null;
}

export function openPatternWorkshop(rawText: string): void {
  const text = rawText.trim().slice(0, 1000);
  if (!text) return;
  closePatternWorkshop();
  const root = document.createElement("aside");
  root.className = "veksha-pattern-workshop";
  root.dataset.avSkip = "1";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-label", deps.t("pattern_workshop_title", "Pattern Workshop"));
  const header = document.createElement("header");
  const title = document.createElement("strong");
  title.textContent = deps.t("pattern_workshop_title", "Pattern Workshop");
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "×";
  close.addEventListener("click", closePatternWorkshop);
  header.append(title, close);
  const status = document.createElement("div");
  status.className = "veksha-pattern-workshop-status";
  status.textContent = deps.t("grammar_analysis_loading", "Analyzing the sentence…");
  root.append(header, status);
  document.documentElement.appendChild(root);
  panel = root;

  void deps.getUsername().then((username) => {
    if (!username) throw new Error("profile required");
    return analyzePatternWorkshop(text, location.href);
  }).then((draft) => {
    if (panel === root) renderDraft(root, draft);
  }).catch(() => {
    if (panel === root) status.textContent = deps.t("grammar_analysis_failed", "Could not analyze the selection. Try again.");
  });
}

function renderDraft(root: HTMLElement, draft: PatternWorkshopDraft): void {
  const status = root.querySelector<HTMLElement>(".veksha-pattern-workshop-status");
  status?.remove();
  const quote = document.createElement("q");
  quote.textContent = draft.text;
  root.appendChild(quote);
  if (!draft.patterns.length) {
    const empty = document.createElement("p");
    empty.textContent = deps.t("grammar_analysis_empty", "No notable grammar found in this selection.");
    root.appendChild(empty);
    return;
  }
  const prompt = document.createElement("p");
  prompt.textContent = deps.t("pattern_workshop_choose", "Choose one construction to practise now.");
  root.appendChild(prompt);
  const choices = document.createElement("div");
  choices.className = "veksha-pattern-workshop-choices";
  for (const pattern of draft.patterns) {
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = `<strong></strong><small></small>`;
    button.querySelector("strong")!.textContent = pattern.label;
    button.querySelector("small")!.textContent = pattern.explanation;
    button.addEventListener("click", () => renderPractice(root, draft, pattern.index));
    choices.appendChild(button);
  }
  root.appendChild(choices);
}

function renderPractice(root: HTMLElement, draft: PatternWorkshopDraft, index: number): void {
  const pattern = draft.patterns[index];
  root.querySelectorAll(":scope > q, :scope > p, :scope > .veksha-pattern-workshop-choices, :scope > .veksha-pattern-practice").forEach((node) => node.remove());
  const practice = document.createElement("form");
  practice.className = "veksha-pattern-practice";
  const title = document.createElement("strong");
  title.textContent = pattern.label;
  const rule = document.createElement("p");
  rule.textContent = pattern.explanation;
  const contrast = document.createElement("p");
  contrast.textContent = pattern.contrast_example;
  const label = document.createElement("label");
  label.textContent = pattern.challenge_prompt;
  const input = document.createElement("input");
  input.required = true;
  input.autocomplete = "off";
  const error = document.createElement("small");
  error.hidden = true;
  error.textContent = deps.t("pattern_workshop_retry", "Not yet — use the construction name shown above.");
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = deps.t("pattern_workshop_complete", "Complete and add to Error Map");
  label.appendChild(input);
  practice.append(title, rule, contrast, label, error, submit);
  practice.addEventListener("submit", (event) => {
    event.preventDefault();
    submit.disabled = true;
    void completePatternWorkshop(draft.draft_id, index, input.value).then(() => {
      practice.replaceChildren();
      const done = document.createElement("p");
      done.textContent = deps.t("pattern_workshop_saved", "Practice complete. This skill is now in your Error Map.");
      practice.appendChild(done);
    }).catch(() => {
      error.hidden = false;
      submit.disabled = false;
      input.focus();
    });
  });
  root.appendChild(practice);
  input.focus();
}
