/** Clean adapter for acquiring a signed YouTube caption timeline. */
import type { TimedCaptionCue } from "../shared/youtubeCaptions";

export interface YouTubeCaptionTrack {
  languageCode: string;
  kind: "asr" | "manual";
}

export interface YouTubeCaptionTimeline {
  ok: boolean;
  cues?: TimedCaptionCue[];
  translatedCues?: TimedCaptionCue[];
  track?: YouTubeCaptionTrack | null;
  retryable?: boolean;
  error?: string;
}

export async function acquireYouTubeCaptionTimeline(
  videoId: string,
  sourceLang: string,
  targetLang: string,
): Promise<YouTubeCaptionTimeline | undefined> {
  return chrome.runtime.sendMessage({
    type: "VEKSHA_YOUTUBE_CAPTIONS",
    videoId,
    sourceLang,
    targetLang,
  }) as Promise<YouTubeCaptionTimeline | undefined>;
}
