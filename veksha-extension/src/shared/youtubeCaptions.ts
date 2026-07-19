export interface YouTubeCaptionTrack {
  baseUrl: string;
  languageCode: string;
  kind?: string;
  name?: { simpleText?: string; runs?: { text?: string }[] };
  vssId?: string;
}

export interface TimedCaptionCue {
  startMs: number;
  endMs: number;
  text: string;
  tokens: string[];
}

function jsonArrayAfter(source: string, markerAt: number): unknown[] | null {
  const start = source.indexOf("[", markerAt);
  if (start < 0) return null;
  let depth = 0;
  let quoted = false;
  let escaped = false;
  for (let i = start; i < source.length; i += 1) {
    const char = source[i];
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
      continue;
    }
    if (char === '"') quoted = true;
    else if (char === "[") depth += 1;
    else if (char === "]") {
      depth -= 1;
      if (depth === 0) {
        try {
          const parsed = JSON.parse(source.slice(start, i + 1));
          return Array.isArray(parsed) ? parsed : null;
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

/** Extract YouTube's signed timed-text URLs without relying on caption DOM nodes. */
export function extractCaptionTracks(html: string): YouTubeCaptionTrack[] {
  const marker = '"captionTracks"';
  let offset = 0;
  while (offset < html.length) {
    const at = html.indexOf(marker, offset);
    if (at < 0) break;
    const parsed = jsonArrayAfter(html, at + marker.length);
    if (parsed) {
      const tracks = parsed.filter((track): track is YouTubeCaptionTrack => {
        if (!track || typeof track !== "object") return false;
        const item = track as Partial<YouTubeCaptionTrack>;
        return typeof item.baseUrl === "string" && typeof item.languageCode === "string";
      });
      if (tracks.length) return tracks;
    }
    offset = at + marker.length;
  }
  return [];
}

function baseLanguage(code: string): string {
  return code.toLowerCase().split(/[-_]/)[0];
}

/** Prefer the requested language; within a language prefer author captions over ASR. */
export function selectCaptionTrack(
  tracks: YouTubeCaptionTrack[], sourceLang: string,
): YouTubeCaptionTrack | null {
  if (!tracks.length) return null;
  let candidates = tracks;
  if (sourceLang && sourceLang !== "auto") {
    const exact = tracks.filter((track) => track.languageCode.toLowerCase() === sourceLang.toLowerCase());
    const sameBase = tracks.filter((track) => baseLanguage(track.languageCode) === baseLanguage(sourceLang));
    candidates = exact.length ? exact : sameBase.length ? sameBase : tracks;
  } else {
    // YouTube orders the original/default caption language first. Restrict the
    // manual-vs-ASR preference to that language so a translated author track
    // cannot accidentally replace the video's spoken language.
    const firstLanguage = baseLanguage(tracks[0].languageCode);
    candidates = tracks.filter((track) => baseLanguage(track.languageCode) === firstLanguage);
  }
  return candidates.find((track) => track.kind !== "asr") ?? candidates[0] ?? null;
}

export function captionTrackJson3Url(baseUrl: string, targetLang?: string): string {
  const url = new URL(baseUrl);
  url.searchParams.set("fmt", "json3");
  if (targetLang) url.searchParams.set("tlang", targetLang);
  return url.toString();
}

/** Convert both author-created and automatic json3 tracks into stable timed cues. */
export function parseJson3Captions(payload: unknown): TimedCaptionCue[] {
  const events = (payload as { events?: unknown[] } | null)?.events;
  if (!Array.isArray(events)) return [];
  const cues: TimedCaptionCue[] = [];
  for (const raw of events) {
    if (!raw || typeof raw !== "object") continue;
    const event = raw as {
      tStartMs?: number; dDurationMs?: number;
      segs?: { utf8?: string }[];
    };
    if (!Number.isFinite(event.tStartMs) || !Array.isArray(event.segs)) continue;
    const text = event.segs
      .map((segment) => typeof segment?.utf8 === "string" ? segment.utf8 : "")
      .join("")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) continue;
    const startMs = Math.max(0, Number(event.tStartMs));
    const durationMs = Number.isFinite(event.dDurationMs) ? Math.max(100, Number(event.dDurationMs)) : 5000;
    const previous = cues[cues.length - 1];
    if (previous && previous.text === text && startMs <= previous.endMs) {
      previous.endMs = Math.max(previous.endMs, startMs + durationMs);
      continue;
    }
    cues.push({
      startMs,
      endMs: startMs + durationMs,
      text,
      tokens: text.split(/\s+/).slice(0, 40),
    });
  }
  return cues;
}

export function findCaptionCue(cues: TimedCaptionCue[], timeMs: number): TimedCaptionCue | null {
  let low = 0;
  let high = cues.length - 1;
  let found = -1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    if (cues[mid].startMs <= timeMs) {
      found = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  if (found < 0) return null;
  const cue = cues[found];
  return timeMs < cue.endMs ? cue : null;
}
