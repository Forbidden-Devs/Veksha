import type { PageSession } from "./page-session";

export class PageReminder {
  private element: HTMLElement | null = null;

  constructor(
    private readonly session: PageSession,
    private readonly startTraining: (username: string) => void,
  ) {}

  show(message: Record<string, unknown>): void {
    this.close();
    const username = typeof message.username === "string" ? message.username : "";
    const dueWords = Math.max(0, Number(message.due_words ?? 0));
    const dueTopic = typeof message.due_topic === "string" ? message.due_topic : "";
    const level = Math.min(3, Math.max(1, Number(message.reminder_level ?? 2)));
    const focusGuard = Boolean(message.overseer) || level >= 3;

    const stage = document.createElement("div");
    stage.className = `vk-reminder-stage${focusGuard ? " is-focus" : ""}`;
    stage.setAttribute("role", focusGuard ? "alertdialog" : "presentation");

    const card = document.createElement("aside");
    card.className = `vk-page-reminder level-${level}`;
    card.setAttribute("role", "dialog");
    const icon = document.createElement("img");
    icon.src = chrome.runtime.getURL("icons/icon48.png");
    icon.alt = "";
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = this.session.t("reminder_title", "Ready for a short practice?");
    const summary = document.createElement("p");
    const parts: string[] = [];
    if (dueWords) parts.push(this.session.t("reminder_words", "{n} words").replace("{n}", String(dueWords)));
    if (dueTopic) parts.push(`${this.session.t("reminder_topic", "lesson")}: ${dueTopic}`);
    summary.textContent = parts.length
      ? parts.join(" · ")
      : this.session.t("reminder_subtitle_default", "Your next review is ready.");
    copy.append(title, summary);

    if (focusGuard) {
      const note = document.createElement("p");
      note.className = "vk-page-reminder-note";
      note.textContent = this.session.t(
        "reminder_focus_note",
        "Choose what happens next so this review does not disappear unnoticed.",
      );
      copy.append(note);
    }

    const actions = document.createElement("div");
    actions.className = "vk-page-reminder-actions";
    const start = document.createElement("button");
    start.type = "button";
    start.textContent = this.session.t("reminder_start", "Start practice");
    start.addEventListener("click", () => {
      this.close();
      if (username) this.startTraining(username);
    });
    actions.append(start);

    if (focusGuard) {
      const snooze = document.createElement("button");
      snooze.type = "button";
      snooze.className = "vk-page-reminder-secondary";
      snooze.textContent = this.session.t("reminder_snooze", "Remind me in 15 minutes");
      snooze.addEventListener("click", () => {
        void chrome.runtime.sendMessage({ type: "VEKSHA_SNOOZE_PRACTICE_REMINDER", minutes: 15 });
        this.close();
      });
      const pause = document.createElement("button");
      pause.type = "button";
      pause.className = "vk-page-reminder-link";
      pause.textContent = this.session.t("reminder_skip_today", "Pause for today");
      pause.addEventListener("click", () => {
        void chrome.runtime.sendMessage({ type: "VEKSHA_PAUSE_PRACTICE_REMINDERS", hours: 24 });
        this.close();
      });
      actions.append(snooze, pause);
    } else {
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "vk-page-reminder-close";
      dismiss.setAttribute("aria-label", this.session.t("reminder_dismiss", "Dismiss"));
      dismiss.textContent = "×";
      dismiss.addEventListener("click", this.close);
      card.append(dismiss);
    }

    card.append(icon, copy, actions);
    stage.appendChild(card);
    document.documentElement.appendChild(stage);
    this.element = stage;
  }

  readonly close = (): void => {
    this.element?.remove();
    this.element = null;
  };
}
