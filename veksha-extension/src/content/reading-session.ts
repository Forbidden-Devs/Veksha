/** Captures one page sample only after the learner starts a Reading Session. */
import { observeReadingSession } from "../shared/api";
import { sampleText } from "./page-text";

export interface ReadingSessionState {
  sessionId: string;
  startedAt: number;
}

const SAMPLE_CHAR_BUDGET = 8000;
let current: ReadingSessionState | null = null;
let lastObservation = "";

export function setReadingSession(session: ReadingSessionState | null): void {
  current = session;
  if (!session) {
    lastObservation = "";
    return;
  }
  void observeCurrentPage();
}

export async function observeCurrentPage(): Promise<void> {
  if (!current) return;
  const observationKey = `${current.sessionId}:${location.href}`;
  if (observationKey === lastObservation) return;
  const text = sampleText(SAMPLE_CHAR_BUDGET);
  if (!text) return;
  lastObservation = observationKey;
  try {
    await observeReadingSession(
      current.sessionId,
      text,
      location.hostname.replace(/^www\./, ""),
    );
  } catch {
    // A closed server-side session cannot silently resume on later pages.
    current = null;
  }
}
