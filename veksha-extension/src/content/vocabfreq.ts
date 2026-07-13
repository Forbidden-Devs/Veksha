/**
 * vocabfreq.ts — "real browsing" personal frequency list.
 *
 * When enabled, samples the page's text once per page load (silently, no
 * page UI) and sends it to the backend to be tokenized and counted against
 * the user's personal word-frequency list, tagged with the site's domain.
 * Viewed later in the "My Words" screen.
 */
import { trackVocabFrequency } from "../shared/api";
import { sampleText } from "./page-text";

export interface VocabFreqDeps {
  getUsername: () => Promise<string | null>;
}

const SAMPLE_CHAR_BUDGET = 8000;

let deps: VocabFreqDeps;
let enabled = false;

export function initVocabFreq(d: VocabFreqDeps): void {
  deps = d;
}

export function isVocabFreqEnabled(): boolean {
  return enabled;
}

export function setVocabFreqEnabled(on: boolean): void {
  if (on === enabled) return;
  enabled = on;
  if (on) void track();
}

function domainOf(): string {
  return location.hostname.replace(/^www\./, "");
}

async function track(): Promise<void> {
  if (!enabled) return;
  const username = await deps.getUsername().catch(() => null);
  if (!username || !enabled) return;

  const text = sampleText(SAMPLE_CHAR_BUDGET);
  if (!text) return;

  try {
    await trackVocabFrequency(text, domainOf());
  } catch (err) {
    console.debug("[vocabfreq] tracking failed:", err);
  }
}
