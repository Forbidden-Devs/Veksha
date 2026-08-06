export type FocusMode = "soft" | "strict";

export interface FocusSession {
  sessionId: string;
  intention: string;
  startedAt: number;
  endsAt: number;
  sites: string[];
  mode: FocusMode;
  graceUntil: Record<string, number>;
}

export function normalizeFocusSite(value: string): string | null {
  const candidate = value.trim().toLowerCase();
  if (!candidate) return null;
  try {
    const url = new URL(candidate.includes("://") ? candidate : `https://${candidate}`);
    return url.hostname.replace(/^www\./, "") || null;
  } catch {
    return null;
  }
}

export function focusSiteForUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (!/^https?:$/.test(url.protocol)) return null;
    return url.hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

export function sessionBlocksUrl(session: FocusSession, value: string, now = Date.now()): boolean {
  if (session.endsAt <= now) return false;
  const site = focusSiteForUrl(value);
  if (!site || !session.sites.some((blocked) => site === blocked || site.endsWith(`.${blocked}`))) return false;
  return (session.graceUntil[site] ?? 0) <= now;
}
