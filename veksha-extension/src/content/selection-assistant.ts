import { explain, quickTranslate } from "../shared/api";
import { canSpeak, speakText } from "../shared/speech";
import { analyzeGrammarSelection, isGrammarLensEnabled } from "./grammar-lens";
import { YT_STUDY_GUARD_SELECTOR } from "./youtube";
import type { PageSession } from "./page-session";

interface TranslationResult {
  text: string;
  detected: string;
  target: string;
}

const MAX_SELECTION_LENGTH = 2_000;
const PANEL_WIDTH = 360;

function eventBelongsToAssistant(target: EventTarget | null): boolean {
  return Boolean((target as HTMLElement | null)?.closest?.(".vk-selection-tools, .vk-assistant-card"));
}

function eventBelongsToVideoStudy(target: EventTarget | null): boolean {
  return Boolean((target as HTMLElement | null)?.closest?.(YT_STUDY_GUARD_SELECTOR));
}

function iconButton(label: string, text: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.textContent = text;
  return button;
}

export class SelectionAssistant {
  private tools: HTMLElement | null = null;
  private card: HTMLElement | null = null;
  private lastText = "";
  private requestVersion = 0;
  private pointer = { x: 40, y: 120 };

  constructor(
    private readonly session: PageSession,
    private readonly isBlocked: () => boolean,
  ) {}

  mount(): void {
    document.addEventListener("pointermove", this.rememberPointer, { capture: true, passive: true });
    document.addEventListener("contextmenu", this.rememberPointer, { capture: true });
    document.addEventListener("mouseup", this.handleSelection);
    document.addEventListener("pointerdown", this.handleOutsidePointer, true);
    document.addEventListener("keydown", this.handleKey, true);
    window.addEventListener("resize", this.close);
    window.addEventListener("scroll", this.close, { passive: true });
  }

  dispose(): void {
    document.removeEventListener("pointermove", this.rememberPointer, true);
    document.removeEventListener("contextmenu", this.rememberPointer, true);
    document.removeEventListener("mouseup", this.handleSelection);
    document.removeEventListener("pointerdown", this.handleOutsidePointer, true);
    document.removeEventListener("keydown", this.handleKey, true);
    window.removeEventListener("resize", this.close);
    window.removeEventListener("scroll", this.close);
    this.close();
  }

  readonly close = (): void => {
    this.requestVersion += 1;
    this.tools?.remove();
    this.card?.remove();
    this.tools = null;
    this.card = null;
  };

  openFromMessage(text: string): void {
    const clean = text.trim().slice(0, MAX_SELECTION_LENGTH);
    if (!clean || this.isBlocked()) return;
    this.openCard(clean, this.pointer.x, this.pointer.y);
  }

  private readonly rememberPointer = (event: MouseEvent | PointerEvent): void => {
    this.pointer = { x: event.clientX, y: event.clientY };
  };

  private readonly handleSelection = (event: MouseEvent): void => {
    if (this.isBlocked() || eventBelongsToAssistant(event.target) || eventBelongsToVideoStudy(event.target)) return;
    window.setTimeout(() => {
      const selection = window.getSelection();
      const text = selection?.toString().trim().slice(0, MAX_SELECTION_LENGTH) ?? "";
      if (!text || !selection?.rangeCount) {
        this.close();
        this.lastText = "";
        return;
      }
      if (text === this.lastText && (this.tools || this.card)) return;
      this.lastText = text;
      const rect = selection.getRangeAt(0).getBoundingClientRect();
      this.showTools(text, rect);
    });
  };

  private readonly handleOutsidePointer = (event: PointerEvent): void => {
    if (eventBelongsToAssistant(event.target) || eventBelongsToVideoStudy(event.target)) return;
    this.close();
  };

  private readonly handleKey = (event: KeyboardEvent): void => {
    if (event.key === "Escape") this.close();
  };

  private showTools(text: string, rect: DOMRect): void {
    this.close();
    const tools = document.createElement("div");
    tools.className = "vk-selection-tools";
    tools.style.left = `${Math.min(window.innerWidth - 86, Math.max(8, rect.right + 8))}px`;
    tools.style.top = `${Math.min(window.innerHeight - 44, Math.max(8, rect.top))}px`;

    const translate = iconButton(this.session.t("content_translate", "Translate selection"), "↗");
    translate.className = "vk-selection-translate";
    translate.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      this.openCard(text, rect.left, rect.bottom + 8);
    });
    tools.appendChild(translate);

    if (isGrammarLensEnabled()) {
      const grammar = iconButton(
        this.session.t("grammar_analyze_selection", "Analyze grammar"),
        "Aa",
      );
      grammar.className = "vk-selection-grammar";
      grammar.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        analyzeGrammarSelection(text);
        this.close();
      });
      tools.appendChild(grammar);
    }

    document.documentElement.appendChild(tools);
    this.tools = tools;
  }

  private openCard(text: string, x: number, y: number): void {
    this.close();
    const card = document.createElement("section");
    card.className = "vk-assistant-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", this.session.t("content_translate", "Translate selection"));
    card.style.left = `${Math.min(window.innerWidth - PANEL_WIDTH - 12, Math.max(12, x))}px`;
    card.style.top = `${Math.min(window.innerHeight - 260, Math.max(12, y))}px`;

    const header = document.createElement("header");
    const brand = document.createElement("span");
    brand.textContent = "VEKSHA";
    const route = document.createElement("small");
    route.textContent = "AUTO";
    const close = iconButton(this.session.t("content_close", "Close"), "×");
    close.addEventListener("click", this.close);
    header.append(brand, route, close);

    const quote = document.createElement("q");
    quote.textContent = text;
    const output = document.createElement("div");
    output.className = "vk-assistant-result is-loading";
    output.textContent = this.session.t("content_translating", "Translating…");

    const details = document.createElement("div");
    details.className = "vk-assistant-details";
    details.hidden = true;

    const actions = document.createElement("footer");
    const listen = iconButton(this.session.t("content_listen", "Listen"), "◖))");
    listen.disabled = true;
    const explainButton = iconButton(this.session.t("content_explain", "More details"), this.session.t("content_explain", "More details"));
    explainButton.disabled = true;
    actions.append(listen, explainButton);
    card.append(header, quote, output, details, actions);
    document.documentElement.appendChild(card);
    this.card = card;

    const version = ++this.requestVersion;
    void this.translate(text).then((result) => {
      if (version !== this.requestVersion || this.card !== card) return;
      output.classList.remove("is-loading");
      output.textContent = result.text;
      route.textContent = `${(result.detected || "AUTO").toUpperCase()} → ${result.target.toUpperCase()}`;
      listen.disabled = !result.detected || !canSpeak();
      explainButton.disabled = false;
      listen.addEventListener("click", () => speakText(text, result.detected));
      explainButton.addEventListener("click", () => {
        void this.loadExplanation(text, result.text, details, explainButton);
      }, { once: true });
    }).catch(() => {
      if (version !== this.requestVersion || this.card !== card) return;
      output.classList.remove("is-loading");
      output.classList.add("is-error");
      output.textContent = this.session.t("content_translation_failed", "Translation failed. Try again.");
    });
  }

  private async translate(text: string): Promise<TranslationResult> {
    const username = await this.session.getUsername();
    if (!username) throw new Error("profile required");
    const nativeTarget = this.session.nativeLang || this.session.translationState.targetLang;
    const first = await quickTranslate(username, text, "auto", nativeTarget, false, location.href);
    const detected = (first.detected_source_lang || "").toLowerCase();
    const studied = this.session.studiedLang.toLowerCase();
    if (detected && studied && studied !== nativeTarget.toLowerCase() && detected === nativeTarget.toLowerCase()) {
      const reverse = await quickTranslate(username, text, "auto", studied, false, location.href);
      return { text: reverse.translation, detected, target: studied };
    }
    return { text: first.translation, detected, target: nativeTarget };
  }

  private async loadExplanation(
    text: string,
    translation: string,
    container: HTMLElement,
    button: HTMLButtonElement,
  ): Promise<void> {
    container.hidden = false;
    container.classList.remove("is-error");
    container.textContent = this.session.t("content_translating", "Loading…");
    button.disabled = true;
    try {
      const username = await this.session.getUsername();
      if (!username) throw new Error("profile required");
      const response = await explain(username, text, translation);
      container.textContent = response.explanation;
    } catch {
      container.classList.add("is-error");
      container.textContent = this.session.t("content_explanation_failed", "Explanation is unavailable.");
      button.disabled = false;
    }
  }
}
