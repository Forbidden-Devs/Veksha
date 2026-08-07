/** Runtime that connects YouTube playback to Dual Subtitles and Subtitle Study. */
import {
  initDualSubs,
  setTimeline as setDualSubsTimeline,
  syncAtTime as syncDualSubsAtTime,
} from "./dualsubs";
import {
  initSubtitleStudy,
  setStudyMedia,
  studyTick,
} from "./subtitle-study";
import { acquireYouTubeCaptionTimeline } from "./youtube";

export interface YouTubeStudyDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
  state: { sourceLang: string; targetLang: string };
}

export const YT_STUDY_GUARD_SELECTOR =
  ".ytp-caption-window-container, .av-dualsub, .av-dualsub-toggle, .av-study-bar, .av-study-card";

const MAX_RETRIES = 4;
let deps: YouTubeStudyDeps;
let loadedVideoId = "";
let loadSequence = 0;
let retryCount = 0;
let retryTimer = 0;
let frame = 0;
let layer: HTMLElement | null = null;

function videoIdFromUrl(): string {
  const url = new URL(location.href);
  if (url.pathname === "/watch") return url.searchParams.get("v") ?? "";
  return url.pathname.match(/^\/(?:shorts|live)\/([\w-]{6,20})/)?.[1] ?? "";
}

function videoElement(): HTMLVideoElement | null {
  return document.querySelector<HTMLVideoElement>("#movie_player video");
}

function playerElement(): HTMLElement | null {
  return document.querySelector<HTMLElement>("#movie_player");
}

function overlayLayer(): HTMLElement | null {
  const player = playerElement();
  if (!player) return null;
  if (layer?.parentElement === player) return layer;
  layer?.remove();
  layer = document.createElement("div");
  layer.className = "av-yt-layer";
  player.appendChild(layer);
  return layer;
}

function captionAnchor(): DOMRect | null {
  const node = document.querySelector<HTMLElement>(".ytp-caption-window-container");
  return node?.getBoundingClientRect() ?? null;
}

function clearTimeline(): void {
  setDualSubsTimeline([]);
  setStudyMedia(null);
}

function scheduleRetry(videoId: string): void {
  if (retryCount >= MAX_RETRIES || videoId !== videoIdFromUrl()) return;
  retryCount += 1;
  window.clearTimeout(retryTimer);
  retryTimer = window.setTimeout(() => {
    loadedVideoId = "";
    void loadTimeline();
  }, retryCount * 800);
}

async function loadTimeline(): Promise<void> {
  const videoId = videoIdFromUrl();
  if (!videoId) {
    loadedVideoId = "";
    clearTimeline();
    return;
  }
  if (videoId === loadedVideoId) return;
  loadedVideoId = videoId;
  retryCount = 0;
  clearTimeline();
  const sequence = ++loadSequence;
  try {
    const timeline = await acquireYouTubeCaptionTimeline(
      videoId,
      deps.state.sourceLang,
      deps.state.targetLang,
    );
    if (sequence !== loadSequence || videoId !== videoIdFromUrl()) return;
    if (!timeline?.ok || !timeline.cues?.length) {
      scheduleRetry(videoId);
      return;
    }
    setDualSubsTimeline(
      timeline.cues,
      timeline.translatedCues ?? [],
      timeline.track?.kind === "asr",
    );
    setStudyMedia({
      media_key: `youtube:${videoId}:${timeline.track?.languageCode ?? "unknown"}:${timeline.track?.kind ?? "manual"}`,
      media_url: `https://www.youtube.com/watch?v=${videoId}`,
      media_title: document.title.replace(/\s*-\s*YouTube\s*$/, "").slice(0, 300),
    }, timeline.cues, timeline.translatedCues ?? []);
  } catch {
    scheduleRetry(videoId);
  }
}

function playbackFrame(): void {
  const video = videoElement();
  if (video) {
    const timeMs = video.currentTime * 1000;
    syncDualSubsAtTime(timeMs, captionAnchor());
    studyTick(timeMs);
  }
  frame = window.requestAnimationFrame(playbackFrame);
}

export function initYouTubeStudy(value: YouTubeStudyDeps): void {
  deps = value;
  initDualSubs({
    getUsername: value.getUsername,
    t: value.t,
    state: value.state,
    getLayer: overlayLayer,
    getPlayer: playerElement,
  });
  initSubtitleStudy({
    getUsername: value.getUsername,
    t: value.t,
    state: value.state,
    getLayer: overlayLayer,
    getPlayer: playerElement,
    getVideo: videoElement,
  });
  document.addEventListener("yt-navigate-finish", () => void loadTimeline());
  window.addEventListener("popstate", () => void loadTimeline());
  window.addEventListener("pagehide", () => {
    window.cancelAnimationFrame(frame);
    window.clearTimeout(retryTimer);
  }, { once: true });
  frame = window.requestAnimationFrame(playbackFrame);
  void loadTimeline();
}
