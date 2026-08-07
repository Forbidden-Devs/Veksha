import { getSettings } from "../shared/api";
import { isAiBlocked, normalizeAiBlocklist } from "../shared/aiBlocklist";
import { CONFIG } from "../shared/config";
import { loadStaticCatalog, UI_LOCALE_STORAGE_KEY } from "../shared/i18n";

export interface PageFeaturePolicy {
  blocked: boolean;
  readingCoach: boolean;
  readingSession: { sessionId: string; startedAt: number } | null;
}

const PROFILE_TIMEOUT_MS = 3_000;

function browserLanguage(): string {
  return (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
}

export class PageSession {
  readonly translationState: { sourceLang: string; targetLang: string } = {
    sourceLang: CONFIG.DEFAULT_SOURCE_LANG,
    targetLang: CONFIG.DEFAULT_TARGET_LANG,
  };

  nativeLang: string = CONFIG.DEFAULT_TARGET_LANG;
  studiedLang = "";

  private username: string | null | undefined;
  private catalogue: Record<string, string> = {};

  readonly t = (key: string, fallback: string): string => this.catalogue[key] ?? fallback;

  readonly getUsername = async (): Promise<string | null> => {
    if (this.username !== undefined) return this.username;
    const read = chrome.storage.local.get([CONFIG.STORAGE_KEY_USERNAME]);
    const timeout = new Promise<never>((_, reject) => {
      window.setTimeout(() => reject(new Error("Profile lookup timed out")), PROFILE_TIMEOUT_MS);
    });
    const stored = await Promise.race([read, timeout]);
    this.username = (stored[CONFIG.STORAGE_KEY_USERNAME] as string | undefined) ?? null;
    return this.username;
  };

  invalidateUsername(): void {
    this.username = undefined;
  }

  async initialize(): Promise<void> {
    await Promise.all([this.refreshProfile(), this.syncTheme()]);
  }

  async refreshProfile(): Promise<void> {
    const stored = await chrome.storage.local.get([CONFIG.STORAGE_KEY_NATIVE_LANG, UI_LOCALE_STORAGE_KEY]);
    const fallback = (stored[CONFIG.STORAGE_KEY_NATIVE_LANG] as string | undefined) ?? browserLanguage();
    const interfaceLocale = String(stored[UI_LOCALE_STORAGE_KEY] ?? browserLanguage());
    this.nativeLang = fallback;
    this.translationState.targetLang = fallback;
    await this.loadCatalogue(interfaceLocale);

    try {
      const username = await this.getUsername();
      if (!username) return;
      const settings = await getSettings(username);
      this.nativeLang = settings.native_lang || fallback;
      this.studiedLang = settings.target_lang || "";
      this.translationState.targetLang = this.nativeLang;
    } catch {
      // Local language remains usable while the account API is unavailable.
    }
  }

  async readPolicy(): Promise<PageFeaturePolicy> {
    const values = await chrome.storage.local.get([
      CONFIG.STORAGE_KEY_AI_BLOCKLIST,
      CONFIG.STORAGE_KEY_READING_COACH,
      CONFIG.STORAGE_KEY_READING_SESSION,
    ]);
    const blocked = isAiBlocked(
      location.href,
      normalizeAiBlocklist(values[CONFIG.STORAGE_KEY_AI_BLOCKLIST]),
    );
    const readingCoach = Boolean(values[CONFIG.STORAGE_KEY_READING_COACH]);
    return {
      blocked,
      readingCoach,
      readingSession: (() => {
        const value = values[CONFIG.STORAGE_KEY_READING_SESSION];
        if (!value || typeof value !== "object") return null;
        const record = value as Record<string, unknown>;
        return typeof record.sessionId === "string" && typeof record.startedAt === "number"
          ? { sessionId: record.sessionId, startedAt: record.startedAt }
          : null;
      })(),
    };
  }

  async syncTheme(): Promise<void> {
    const values = await chrome.storage.local.get(["vk_theme"]);
    document.documentElement.dataset.vkTheme = String(values.vk_theme ?? "light");
  }

  private async loadCatalogue(lang: string): Promise<void> {
    try {
      this.catalogue = await loadStaticCatalog(lang) as unknown as Record<string, string>;
    } catch {
      this.catalogue = {};
    }
  }
}
