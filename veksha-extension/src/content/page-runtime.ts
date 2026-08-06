import { CONFIG } from "../shared/config";
import { initReadingCoach, refreshReadingCoach, setReadingCoachEnabled } from "./reading-coach";
import { closePatternWorkshop, initPatternWorkshop } from "./pattern-workshop";
import { closeOverlay, showLessonOverlay, showTrainingOverlay } from "./overlay";
import type { GoalTarget } from "../popup/overlays/GoalWindow";
import { PageSession, type PageFeaturePolicy } from "./page-session";
import { SelectionAssistant } from "./selection-assistant";
import { observeCurrentPage, setReadingSession } from "./reading-session";
import { initYouTubeStudy } from "./youtube-study-runtime";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

class PageRuntime {
  private readonly session = new PageSession();
  private readonly selection = new SelectionAssistant(this.session, () => this.blocked);
  private blocked = true;
  private currentUrl = location.href;
  private routeTimer = 0;

  async start(): Promise<void> {
    document.documentElement.dataset.vekshaAiBlocked = "true";
    await this.session.initialize();

    initReadingCoach({ getUsername: this.session.getUsername, t: this.session.t });
    initPatternWorkshop({ getUsername: this.session.getUsername, t: this.session.t });
    if (/(^|\.)youtube\.com$/.test(location.hostname)) {
      initYouTubeStudy({
        getUsername: this.session.getUsername,
        t: this.session.t,
        state: this.session.translationState,
      });
    }

    this.selection.mount();
    chrome.runtime.onMessage.addListener(this.onMessage);
    chrome.storage.onChanged.addListener(this.onStorageChanged);
    window.addEventListener("pagehide", this.dispose, { once: true });
    this.routeTimer = window.setInterval(this.observeRoute, 800);
    await this.refreshPolicy();
  }

  private readonly refreshPolicy = async (): Promise<void> => {
    try {
      this.applyPolicy(await this.session.readPolicy());
    } catch {
      this.applyPolicy({
        blocked: true,
        readingCoach: false,
        readingSession: null,
      });
    }
  };

  private applyPolicy(policy: PageFeaturePolicy): void {
    this.blocked = policy.blocked;
    document.documentElement.dataset.vekshaAiBlocked = String(policy.blocked);
    if (policy.blocked) {
      this.selection.close();
      closeOverlay();
    }
    setReadingCoachEnabled(!policy.blocked && policy.readingCoach);
    setReadingSession(!policy.blocked ? policy.readingSession : null);
    document.dispatchEvent(new CustomEvent("VEKSHA_AI_BLOCK_STATE", {
      detail: { blocked: policy.blocked },
    }));
  }

  private readonly observeRoute = (): void => {
    if (location.href === this.currentUrl) return;
    this.currentUrl = location.href;
      this.selection.close();
      closePatternWorkshop();
    void this.refreshPolicy().then(() => {
      refreshReadingCoach();
      void observeCurrentPage();
    });
  };

  private readonly onStorageChanged = (
    changes: Record<string, chrome.storage.StorageChange>,
    area: string,
  ): void => {
    if (area !== "local") return;
    if (changes.vk_theme) {
      document.documentElement.dataset.vkTheme = String(changes.vk_theme.newValue ?? "light");
    }
    if (changes[CONFIG.STORAGE_KEY_USERNAME]) this.session.invalidateUsername();
    if (changes[CONFIG.STORAGE_KEY_NATIVE_LANG]) void this.session.refreshProfile();
    if (changes[CONFIG.STORAGE_KEY_AI_BLOCKLIST]) void this.refreshPolicy();
  };

  private readonly onMessage = (message: unknown): void => {
    if (!isRecord(message) || typeof message.type !== "string") return;
    switch (message.type) {
      case "VEKSHA_PING":
        return;
      case "VEKSHA_OPEN_TRAINING":
        if (typeof message.username === "string") showTrainingOverlay(message.username);
        return;
      case "VEKSHA_OPEN_LESSON":
        if (typeof message.username === "string" && message.target) {
          showLessonOverlay(
            message.username,
            message.target as GoalTarget,
            typeof message.title === "string" ? message.title : undefined,
          );
        }
        return;
      case "VEKSHA_AI_BLOCKLIST_UPDATED":
        void this.refreshPolicy();
        return;
      case "VEKSHA_TOGGLE_READING_COACH":
        if (!this.blocked) setReadingCoachEnabled(Boolean(message.enabled));
        return;
      case "VEKSHA_READING_SESSION_CHANGED":
        void this.refreshPolicy();
        return;
      case "VEKSHA_TRANSLATE_SELECTION":
        if (typeof message.text === "string") this.selection.openFromMessage(message.text);
        return;
    }
  };

  private readonly dispose = (): void => {
    window.clearInterval(this.routeTimer);
    this.selection.dispose();
    chrome.runtime.onMessage.removeListener(this.onMessage);
    chrome.storage.onChanged.removeListener(this.onStorageChanged);
  };
}

export async function startPageRuntime(): Promise<void> {
  await new PageRuntime().start();
}
