/**
 * subtitle-study.ts — the study session that sits on top of dual subtitles.
 *
 * dualsubs.ts renders a parallel translation; this module turns the same track
 * into a controlled session:
 *
 *   • what is shown        — original, translation, both, neither, or on tap,
 *                            plus an automatic pause at the end of each line
 *   • how it is replayed   — single replay, loop, slow motion, all with the
 *                            padding the backend computes so a fragment never
 *                            clips its own first syllable
 *   • what is asked        — a comprehension check every few lines, built from
 *                            the real cue and its neighbours
 *   • what is kept         — a word saved with its timecode, and a cloze built
 *                            out of the line it was actually spoken in
 *
 * Line identities come from the backend (see api/subtitle_study.py): this
 * module only ever sends cues. Progress is flushed in batches so a video does
 * not turn into one request per subtitle.
 */
import {
  studyBuildCloze,
  studyCheckAnswer,
  studyCloseSession,
  studyCreateCheck,
  studyPlanFragment,
  studyRecordProgress,
  studySaveWord,
  studySetDisplay,
  studyStartSession,
  studyWordSenses,
  type StudyCheck,
  type StudyCloze,
  type StudyCue,
  type StudyDisplay,
  type StudyFragment,
  type StudyMediaRef,
  type StudySense,
  type StudySummary,
} from "../shared/api";
import { CONFIG } from "../shared/config";
import type { TimedCaptionCue } from "../shared/youtubeCaptions";

export interface SubtitleStudyDeps {
  getUsername: () => Promise<string | null>;
  t: (key: string, fallback: string) => string;
  state: { sourceLang: string; targetLang: string };
  getLayer: () => HTMLElement | null;
  getPlayer: () => HTMLElement | null;
  getVideo: () => HTMLVideoElement | null;
}

/** Context cues sent along with a fragment or a check request. */
const WINDOW_BEFORE = 4;
const WINDOW_AFTER = 4;
const PROGRESS_FLUSH_MS = 6000;
const MAX_QUEUED_EVENTS = 20;
const SLOW_RATE = 0.7;

const DISPLAY_CYCLE: Array<{ key: string; label: string; display: Partial<StudyDisplay> }> = [
  { key: "dual", label: "AB", display: { show_original: true, show_translation: true, reveal_on_tap: false } },
  { key: "original", label: "A", display: { show_original: true, show_translation: false, reveal_on_tap: false } },
  { key: "translation", label: "B", display: { show_original: false, show_translation: true, reveal_on_tap: false } },
  { key: "reveal_on_tap", label: "?", display: { show_original: true, show_translation: true, reveal_on_tap: true } },
  { key: "hidden", label: "—", display: { show_original: false, show_translation: false, reveal_on_tap: false } },
];

let deps: SubtitleStudyDeps;
let initialized = false;

// Feature state
let studyRequested = false;
let dualSubsAvailable = false;
let featureEnabled = false;
let media: StudyMediaRef | null = null;
let cues: TimedCaptionCue[] = [];
let translations: TimedCaptionCue[] = [];
let sessionId = "";
let display: StudyDisplay = {
  show_original: true,
  show_translation: true,
  reveal_on_tap: false,
  auto_pause: false,
};
let checkDue = false;
let sessionGeneration = 0;

// Playback state
let currentIndex = -1;
/** Survives the gaps between cues, so a pause between lines still has a line. */
let lastCueIndex = -1;
let revealed = false;
let autoPausedForIndex = -1;
let loop: StudyFragment | null = null;
let loopsLeft = 0;
let restoreRate = 1;

// Progress batching
let queue: Array<{ kind: "watched" | "replayed"; cue: StudyCue; slowed?: boolean }> = [];
let flushTimer = 0;
let flushing = false;

// UI
let barEl: HTMLElement | null = null;
let cardEl: HTMLElement | null = null;
let pendingCheck: StudyCheck | null = null;

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

export function initSubtitleStudy(d: SubtitleStudyDeps): void {
  if (initialized) return;
  initialized = true;
  deps = d;

  chrome.storage.local.get(
    [CONFIG.STORAGE_KEY_SUBTITLE_STUDY, CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE],
    (res) => {
      studyRequested = Boolean(res[CONFIG.STORAGE_KEY_SUBTITLE_STUDY]);
      dualSubsAvailable = Boolean(res[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE]);
      syncFeatureEnabled();
    },
  );
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    const study = changes[CONFIG.STORAGE_KEY_SUBTITLE_STUDY];
    const dualSubs = changes[CONFIG.STORAGE_KEY_DUAL_SUBS_FEATURE];
    if (!study && !dualSubs) return;
    if (study) studyRequested = Boolean(study.newValue);
    if (dualSubs) dualSubsAvailable = Boolean(dualSubs.newValue);
    syncFeatureEnabled();
  });

  // A tap anywhere on the subtitles reveals the hidden line for its duration.
  document.addEventListener("click", onDocumentClick, true);
  document.addEventListener("VEKSHA_AI_BLOCK_STATE", ((event: CustomEvent<{ blocked: boolean }>) => {
    if (event.detail.blocked) teardown();
  }) as EventListener);
  window.addEventListener("pagehide", () => void flushProgress(true), { once: true });
}

/** A study session runs only while both flags hold.
 *
 *  The session hides, reveals and loops a translated line, so it cannot outlive
 *  dual subtitles: switching those off switches the session off with them, the
 *  mirror of switching them on together. Reading both flags here rather than
 *  trusting the popup to clear one keeps that true whoever writes the storage.
 */
function syncFeatureEnabled(): void {
  const next = studyRequested && dualSubsAvailable;
  if (featureEnabled === next) return;
  featureEnabled = next;
  if (!featureEnabled) {
    teardown();
    return;
  }
  if (media) void openSession();
}

/** Called by youtube.ts once a video's timed track is available. */
export function setStudyMedia(
  ref: StudyMediaRef | null,
  sourceCues: TimedCaptionCue[] = [],
  translatedCues: TimedCaptionCue[] = [],
): void {
  sessionGeneration += 1;
  void flushProgress(true);
  media = ref;
  cues = sourceCues;
  translations = translatedCues;
  sessionId = "";
  currentIndex = -1;
  lastCueIndex = -1;
  autoPausedForIndex = -1;
  revealed = false;
  stopLoop();
  closeCard();
  if (!ref || !cues.length) {
    applyDisplay();
    syncBar();
    return;
  }
  if (featureEnabled) void openSession();
}

async function openSession(): Promise<void> {
  if (!media || !featureEnabled) return;
  const generation = sessionGeneration;
  const username = await deps.getUsername().catch(() => null);
  if (!username || generation !== sessionGeneration || !media) return;
  try {
    const session = await studyStartSession(media, display);
    if (generation !== sessionGeneration) return;
    sessionId = session.session_id;
    display = session.display;
    checkDue = session.check_due;
    applyDisplay();
    syncBar();
    if (session.resumed && session.cursor_ms > 0) offerResume(session.cursor_ms, session.lines_watched);
  } catch (error) {
    console.debug("[Veksha][study] session unavailable", error);
  }
}

function teardown(): void {
  // Send what the session already knows before letting go of its id, so
  // switching the feature off does not cost the last few lines of progress.
  void flushProgress(true);
  sessionGeneration += 1;
  sessionId = "";
  stopLoop();
  closeCard();
  barEl?.remove();
  barEl = null;
  const player = deps?.getPlayer();
  player?.classList.remove("av-study-hide-original", "av-study-hide-translation");
}

// ---------------------------------------------------------------------------
// Playback tick — driven from youtube.ts' animation frame
// ---------------------------------------------------------------------------

export function studyTick(timeMs: number): void {
  if (!featureEnabled || !media || !cues.length) return;
  driveLoop(timeMs);
  const index = indexAt(timeMs);
  if (index !== currentIndex) {
    currentIndex = index;
    revealed = false;
    if (index >= 0) {
      lastCueIndex = index;
      enqueue({ kind: "watched", cue: toCue(cues[index], translations[index]) });
      applyDisplay();
    }
    // The bar only changes when the line does; this runs on every animation
    // frame, so nothing else here may touch the DOM.
    syncBar();
  }
  if (index >= 0) maybeInterrupt(timeMs, index);
}

function activeIndex(): number {
  return currentIndex >= 0 ? currentIndex : lastCueIndex;
}

function indexAt(timeMs: number): number {
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
  if (found < 0) return -1;
  return timeMs < cues[found].endMs ? found : -1;
}

/** Stop at the end of a line — once, and only while the line is still on screen.
 *
 *  A due comprehension check interrupts whether or not automatic pausing is on:
 *  the check *is* the pause, and it is what the session is counting lines
 *  towards. Automatic pausing is the weaker, always-on version of the same idea.
 */
function maybeInterrupt(timeMs: number, index: number): void {
  if (loop || autoPausedForIndex === index) return;
  if (timeMs < cues[index].endMs - 120) return;
  if (checkDue && !cardEl) {
    autoPausedForIndex = index;
    void askComprehension(index);
    return;
  }
  if (!display.auto_pause) return;
  autoPausedForIndex = index;
  pause();
}

// ---------------------------------------------------------------------------
// Fragment replay
// ---------------------------------------------------------------------------

async function replayFragment(
  index: number,
  options: { repeats?: number; rate?: number; afterError?: boolean } = {},
): Promise<void> {
  if (!media || index < 0 || index >= cues.length) return;
  const window = cues
    .slice(Math.max(0, index - WINDOW_BEFORE), index + 1 + WINDOW_AFTER)
    .map((cue, offset) => toCue(cue, translations[Math.max(0, index - WINDOW_BEFORE) + offset]));
  const video = deps.getVideo();
  try {
    const fragment = await studyPlanFragment(media, window, toCue(cues[index], translations[index]), {
      playbackRate: options.rate ?? 1,
      repeats: options.repeats ?? 1,
      mediaDurationMs: video && Number.isFinite(video.duration) ? Math.round(video.duration * 1000) : 0,
      afterError: options.afterError ?? false,
      sessionId,
    });
    startLoop(fragment);
  } catch (error) {
    console.debug("[Veksha][study] fragment unavailable", error);
  }
}

function startLoop(fragment: StudyFragment): void {
  const video = deps.getVideo();
  if (!video) return;
  if (!loop) restoreRate = video.playbackRate;
  loop = fragment;
  loopsLeft = fragment.repeats;
  video.playbackRate = fragment.playback_rate;
  video.currentTime = fragment.start_ms / 1000;
  autoPausedForIndex = -1;
  void video.play().catch(() => undefined);
  syncBar();
}

function driveLoop(timeMs: number): void {
  if (!loop) return;
  // A seek well outside the window is the learner taking the wheel back.
  if (timeMs < loop.start_ms - 2000 || timeMs > loop.end_ms + 2000) {
    stopLoop();
    return;
  }
  if (timeMs < loop.end_ms) return;
  const video = deps.getVideo();
  if (!video) return;
  if (loop.looping || loopsLeft > 1) {
    if (!loop.looping) loopsLeft -= 1;
    video.currentTime = loop.start_ms / 1000;
    return;
  }
  stopLoop();
}

function stopLoop(): void {
  if (!loop) return;
  loop = null;
  loopsLeft = 0;
  const video = deps?.getVideo();
  if (video) video.playbackRate = restoreRate || 1;
  syncBar();
}

// ---------------------------------------------------------------------------
// Display modes
// ---------------------------------------------------------------------------

/** Both rows are hidden with a class on the player, so dualsubs.ts stays out of it. */
function translationVisible(): boolean {
  if (!featureEnabled || !sessionId) return true;
  return display.reveal_on_tap ? revealed : display.show_translation;
}

function originalVisible(): boolean {
  if (!featureEnabled || !sessionId) return true;
  return display.reveal_on_tap ? revealed : display.show_original;
}

function applyDisplay(): void {
  const player = deps.getPlayer();
  if (!player) return;
  // Hidden captions stay in the layout and keep their pointer targets: a tap on
  // the subtitle bar is how the learner reveals the line they just missed.
  player.classList.toggle("av-study-hide-original", !originalVisible());
  player.classList.toggle("av-study-hide-translation", !translationVisible());
}

function onDocumentClick(event: MouseEvent): void {
  if (!featureEnabled || !sessionId || !display.reveal_on_tap || revealed) return;
  const target = event.target as HTMLElement | null;
  if (!target?.closest(".ytp-caption-window-container, .av-dualsub, .av-study-reveal")) return;
  revealed = true;
  applyDisplay();
  syncBar();
}

async function setDisplay(next: StudyDisplay): Promise<void> {
  display = next;
  revealed = false;
  applyDisplay();
  syncBar();
  if (!sessionId) return;
  try {
    const session = await studySetDisplay(sessionId, next);
    display = session.display;
    checkDue = session.check_due;
    applyDisplay();
    syncBar();
  } catch (error) {
    console.debug("[Veksha][study] display not stored", error);
  }
}

function currentModeIndex(): number {
  const found = DISPLAY_CYCLE.findIndex(
    (entry) =>
      entry.display.show_original === display.show_original
      && entry.display.show_translation === display.show_translation
      && entry.display.reveal_on_tap === display.reveal_on_tap,
  );
  return found < 0 ? 0 : found;
}

// ---------------------------------------------------------------------------
// Progress batching
// ---------------------------------------------------------------------------

function enqueue(event: { kind: "watched" | "replayed"; cue: StudyCue; slowed?: boolean }): void {
  if (!sessionId) return;
  queue.push(event);
  if (queue.length >= MAX_QUEUED_EVENTS) {
    void flushProgress();
    return;
  }
  if (!flushTimer) flushTimer = window.setTimeout(() => void flushProgress(), PROGRESS_FLUSH_MS);
}

async function flushProgress(force = false): Promise<void> {
  window.clearTimeout(flushTimer);
  flushTimer = 0;
  if (flushing && !force) return;
  if (!sessionId || !media || !queue.length) return;
  const batch = queue.splice(0, MAX_QUEUED_EVENTS);
  const generation = sessionGeneration;
  flushing = true;
  try {
    const session = await studyRecordProgress(sessionId, media.media_key, batch);
    if (generation !== sessionGeneration) return;
    checkDue = session.check_due;
    if (session.display) {
      display = session.display;
      applyDisplay();
    }
    syncBar();
  } catch (error) {
    console.debug("[Veksha][study] progress not stored", error);
  } finally {
    flushing = false;
  }
}

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

function syncBar(): void {
  if (!featureEnabled || !sessionId) {
    barEl?.remove();
    barEl = null;
    return;
  }
  const layer = deps.getLayer();
  if (!layer) return;
  if (!barEl || barEl.parentElement !== layer) {
    barEl?.remove();
    barEl = buildBar();
    layer.appendChild(barEl);
  }
  const mode = DISPLAY_CYCLE[currentModeIndex()];
  setFace(barEl, "mode", mode.label);
  toggleFace(barEl, "pause", display.auto_pause);
  toggleFace(barEl, "loop", Boolean(loop?.looping));
  toggleFace(barEl, "slow", Boolean(loop && loop.playback_rate < 1));
  const revealBtn = barEl.querySelector<HTMLElement>('[data-study="reveal"]');
  if (revealBtn) revealBtn.hidden = !display.reveal_on_tap || revealed;
}

function buildBar(): HTMLElement {
  const bar = document.createElement("div");
  bar.className = "av-study-bar";
  bar.addEventListener("mousedown", (event) => event.stopPropagation());
  bar.addEventListener("click", (event) => event.stopPropagation());

  bar.append(
    button("mode", "AB", deps.t("study_display_mode", "Subtitle display"), () => {
      const next = DISPLAY_CYCLE[(currentModeIndex() + 1) % DISPLAY_CYCLE.length];
      void setDisplay({ ...display, ...next.display } as StudyDisplay);
    }),
    button("reveal", "👁", deps.t("study_reveal", "Show this line"), () => {
      revealed = true;
      applyDisplay();
      syncBar();
    }),
    button("replay", "⟲", deps.t("study_replay", "Replay this line"), () => {
      void replayFragment(activeIndex());
    }),
    button("loop", "∞", deps.t("study_loop", "Loop this line"), () => {
      if (loop?.looping) stopLoop();
      else void replayFragment(activeIndex(), { repeats: 0 });
    }),
    button("slow", "0.7×", deps.t("study_slow", "Slow motion"), () => {
      if (loop && loop.playback_rate < 1) stopLoop();
      else void replayFragment(activeIndex(), { repeats: 0, rate: SLOW_RATE });
    }),
    button("pause", "⏸", deps.t("study_auto_pause", "Pause after each line"), () => {
      void setDisplay({ ...display, auto_pause: !display.auto_pause });
    }),
    button("check", "?", deps.t("study_check", "Check understanding"), () => {
      void askComprehension(activeIndex());
    }),
    button("summary", "▤", deps.t("study_summary", "Session summary"), () => {
      void showSummary();
    }),
  );
  return bar;
}

function button(name: string, face: string, title: string, onClick: () => void): HTMLElement {
  const el = document.createElement("button");
  el.className = "av-study-btn";
  el.dataset.study = name;
  el.textContent = face;
  el.title = title;
  el.setAttribute("aria-label", title);
  el.addEventListener("click", (event) => {
    event.stopPropagation();
    onClick();
  });
  return el;
}

function setFace(root: HTMLElement, name: string, face: string): void {
  const el = root.querySelector<HTMLElement>(`[data-study="${name}"]`);
  if (el) el.textContent = face;
}

function toggleFace(root: HTMLElement, name: string, active: boolean): void {
  root.querySelector<HTMLElement>(`[data-study="${name}"]`)?.classList.toggle("av-study-on", active);
}

// ---------------------------------------------------------------------------
// Cards (comprehension, saving, cloze, summary)
// ---------------------------------------------------------------------------

function openCard(title: string): HTMLElement | null {
  const layer = deps.getLayer();
  if (!layer) return null;
  closeCard();
  cardEl = document.createElement("div");
  cardEl.className = "av-study-card";
  cardEl.addEventListener("mousedown", (event) => event.stopPropagation());
  cardEl.addEventListener("click", (event) => event.stopPropagation());

  const head = document.createElement("div");
  head.className = "av-study-card-head";
  const heading = document.createElement("span");
  heading.textContent = title;
  const close = document.createElement("button");
  close.className = "av-study-close";
  close.textContent = "✕";
  close.title = deps.t("study_close", "Close");
  close.addEventListener("click", () => {
    closeCard();
    resume();
  });
  head.append(heading, close);

  const body = document.createElement("div");
  body.className = "av-study-card-body";
  cardEl.append(head, body);
  layer.appendChild(cardEl);
  return body;
}

function closeCard(): void {
  cardEl?.remove();
  cardEl = null;
  pendingCheck = null;
}

function pause(): void {
  const video = deps.getVideo();
  if (video && !video.paused) video.pause();
}

function resume(): void {
  const video = deps.getVideo();
  if (video?.paused) void video.play().catch(() => undefined);
}

async function askComprehension(index: number): Promise<void> {
  if (!media || index < 0 || index >= cues.length) return;
  pause();
  const body = openCard(deps.t("study_check_title", "Did you follow that?"));
  if (!body) return;
  body.textContent = deps.t("study_loading", "One moment…");
  const start = Math.max(0, index - WINDOW_BEFORE);
  const window = cues
    .slice(start, index + 1 + WINDOW_AFTER)
    .map((cue, offset) => toCue(cue, translations[start + offset]));
  try {
    const check = await studyCreateCheck(media, window, toCue(cues[index], translations[index]), {
      sessionId,
    });
    if (!cardEl) return;
    pendingCheck = check;
    checkDue = false;
    renderCheck(body, check, index);
  } catch (error) {
    body.textContent = `⚠ ${(error as Error).message}`;
  }
}

function renderCheck(body: HTMLElement, check: StudyCheck, index: number): void {
  body.textContent = "";

  const question = document.createElement("p");
  question.className = "av-study-question";
  question.textContent = check.options.length
    ? promptFor(check.kind)
    : check.question;
  body.appendChild(question);

  const hear = document.createElement("button");
  hear.className = "av-study-secondary";
  hear.textContent = deps.t("study_hear_again", "Hear it again");
  hear.addEventListener("click", () => void replayFragment(index));
  body.appendChild(hear);

  const verdict = document.createElement("p");
  verdict.className = "av-study-verdict";
  verdict.hidden = true;

  if (check.options.length) {
    const list = document.createElement("div");
    list.className = "av-study-options";
    check.options.forEach((option) => {
      const choice = document.createElement("button");
      choice.className = "av-study-option";
      choice.textContent = option;
      choice.addEventListener("click", () => {
        list.querySelectorAll("button").forEach((el) => (el.disabled = true));
        void submitAnswer(option, verdict, index);
      });
      list.appendChild(choice);
    });
    body.append(list, verdict);
    return;
  }

  const input = document.createElement("textarea");
  input.className = "av-study-input";
  input.rows = 3;
  input.placeholder = deps.t("study_answer_placeholder", "Answer in your own words");
  const submit = document.createElement("button");
  submit.className = "av-study-primary";
  submit.textContent = deps.t("study_submit", "Check");
  submit.addEventListener("click", () => {
    submit.disabled = true;
    void submitAnswer(input.value, verdict, index);
  });
  body.append(input, submit, verdict);
  input.focus();
}

async function submitAnswer(answer: string, verdict: HTMLElement, index: number): Promise<void> {
  if (!pendingCheck) return;
  const check = pendingCheck;
  verdict.hidden = false;
  verdict.textContent = deps.t("study_loading", "One moment…");
  try {
    const result = await studyCheckAnswer(check.check_id, answer, sessionId);
    if (result.display) {
      display = result.display;
      applyDisplay();
      syncBar();
    }
    verdict.classList.toggle("av-study-wrong", !result.passed);
    verdict.textContent = result.passed
      ? result.feedback || deps.t("study_correct", "Right — that is what was said.")
      : [result.feedback, result.expected_answer].filter(Boolean).join(" — ")
        || deps.t("study_wrong", "Not quite.");
    if (!result.passed) {
      // Straight back to the problem area, starting one line earlier so the
      // fragment arrives with the context that set it up.
      const again = document.createElement("button");
      again.className = "av-study-secondary";
      again.textContent = deps.t("study_back_to_line", "Back to that moment");
      again.addEventListener("click", () => {
        closeCard();
        void replayFragment(index, { afterError: true });
      });
      verdict.after(again);
    }
  } catch (error) {
    verdict.textContent = `⚠ ${(error as Error).message}`;
  } finally {
    pendingCheck = null;
  }
}

function promptFor(kind: string): string {
  if (kind === "which_word") return deps.t("study_which_word", "Which word was spoken?");
  if (kind === "next_line") return deps.t("study_next_line", "Which line comes next?");
  return deps.t("study_check_title", "Did you follow that?");
}

// ---------------------------------------------------------------------------
// Saving a word with its timecode
// ---------------------------------------------------------------------------

/** Entry point used by the caption popup's save button. */
export async function saveSelectedTerm(term: string): Promise<void> {
  const index = activeIndex();
  if (!media || !sessionId || index < 0) return;
  pause();
  const cue = toCue(cues[index], translations[index]);
  const body = openCard(deps.t("study_save_title", "Save with the moment"));
  if (!body) return;
  body.textContent = deps.t("study_loading", "One moment…");
  try {
    const senses = await studyWordSenses(media, term, cue);
    if (!cardEl) return;
    renderSenses(body, term, cue, senses.known_senses, senses.suggestion, senses.needs_disambiguation);
  } catch (error) {
    body.textContent = `⚠ ${(error as Error).message}`;
  }
}

function renderSenses(
  body: HTMLElement,
  term: string,
  cue: StudyCue,
  known: StudySense[],
  suggestion: StudySense | null,
  needsChoice: boolean,
): void {
  body.textContent = "";

  const line = document.createElement("p");
  line.className = "av-study-line";
  line.textContent = cue.text;
  body.appendChild(line);

  if (needsChoice) {
    const note = document.createElement("p");
    note.className = "av-study-note";
    note.textContent = deps.t(
      "study_pick_sense",
      "You already track this spelling. Pick the meaning you heard — different meanings stay separate cards.",
    );
    body.appendChild(note);
  }

  const options = document.createElement("div");
  options.className = "av-study-senses";
  const candidates = [...known, ...(suggestion ? [suggestion] : [])];
  candidates.forEach((sense) => {
    const choice = document.createElement("button");
    choice.className = "av-study-sense";
    choice.textContent = sense.translation;
    if (sense.item_id) choice.title = sense.latest_context;
    choice.addEventListener("click", () => {
      options.querySelectorAll("button").forEach((el) => (el.disabled = true));
      void commitSave(body, term, sense.translation, sense.transcription, cue);
    });
    options.appendChild(choice);
  });
  body.appendChild(options);

  const custom = document.createElement("input");
  custom.className = "av-study-input";
  custom.placeholder = deps.t("study_own_meaning", "…or type the meaning here");
  const save = document.createElement("button");
  save.className = "av-study-primary";
  save.textContent = deps.t("study_save", "Save");
  save.addEventListener("click", () => {
    const translation = custom.value.trim();
    if (!translation) return;
    save.disabled = true;
    void commitSave(body, term, translation, "", cue);
  });
  body.append(custom, save);
}

async function commitSave(
  body: HTMLElement,
  term: string,
  translation: string,
  transcription: string,
  cue: StudyCue,
): Promise<void> {
  if (!media) return;
  try {
    const saved = await studySaveWord(media, term, translation, cue, {
      transcription,
      sessionId,
    });
    if (!cardEl) return;
    body.textContent = "";
    const done = document.createElement("p");
    done.className = "av-study-note";
    done.textContent = `${saved.term} → ${saved.translation} · ${timecode(saved.anchor.start_ms)}`;
    const practise = document.createElement("button");
    practise.className = "av-study-primary";
    practise.textContent = deps.t("study_practise_line", "Practise this line");
    practise.addEventListener("click", () => void openCloze(term, cue));
    body.append(done, practise);
  } catch (error) {
    body.textContent = `⚠ ${(error as Error).message}`;
  }
}

// ---------------------------------------------------------------------------
// Cloze from the real line
// ---------------------------------------------------------------------------

async function openCloze(surface: string, cue: StudyCue): Promise<void> {
  if (!media) return;
  const body = openCard(deps.t("study_cloze_title", "Fill in what was said"));
  if (!body) return;
  body.textContent = deps.t("study_loading", "One moment…");
  try {
    const exercise = await studyBuildCloze(media, cue, surface);
    if (!cardEl) return;
    renderCloze(body, exercise);
  } catch (error) {
    // The backend refuses blanks that would leave an unanswerable puzzle; say so
    // instead of showing a broken exercise.
    body.textContent = `⚠ ${(error as Error).message}`;
  }
}

function renderCloze(body: HTMLElement, exercise: StudyCloze): void {
  body.textContent = "";

  const prompt = document.createElement("p");
  prompt.className = "av-study-cloze";
  prompt.textContent = exercise.prompt;

  const hear = document.createElement("button");
  hear.className = "av-study-secondary";
  hear.textContent = deps.t("study_hear_first", "Hear the fragment");
  hear.addEventListener("click", () => void replayAnchor(exercise));

  const input = document.createElement("input");
  input.className = "av-study-input";
  input.placeholder = deps.t("study_cloze_placeholder", "The missing words");

  const verdict = document.createElement("p");
  verdict.className = "av-study-verdict";
  verdict.hidden = true;

  const hints = document.createElement("div");
  hints.className = "av-study-hints";
  const letter = document.createElement("button");
  letter.className = "av-study-secondary";
  letter.textContent = deps.t("study_hint_letter", "First letter");
  letter.addEventListener("click", () => {
    letter.disabled = true;
    letter.textContent = `${exercise.first_letter}… (${exercise.letter_count})`;
  });
  const translation = document.createElement("button");
  translation.className = "av-study-secondary";
  translation.textContent = deps.t("study_hint_translation", "Translation");
  translation.hidden = !exercise.translation;
  translation.addEventListener("click", () => {
    translation.disabled = true;
    translation.textContent = exercise.translation;
  });
  hints.append(letter, translation);

  const submit = document.createElement("button");
  submit.className = "av-study-primary";
  submit.textContent = deps.t("study_submit", "Check");
  submit.addEventListener("click", () => {
    const given = input.value.trim().toLocaleLowerCase();
    const expected = exercise.answer.trim().toLocaleLowerCase();
    verdict.hidden = false;
    const right = given === expected;
    verdict.classList.toggle("av-study-wrong", !right);
    // Right or wrong, the comparison the learner needs is against the
    // recording, not against a string — so the original plays either way.
    verdict.textContent = right
      ? `✓ ${exercise.answer}`
      : `${deps.t("study_cloze_answer", "It was")}: ${exercise.answer}`;
    void replayAnchor(exercise);
  });

  body.append(prompt, hear, input, hints, submit, verdict);
  input.focus();
}

async function replayAnchor(exercise: StudyCloze): Promise<void> {
  const index = cues.findIndex(
    (cue) => cue.startMs === exercise.anchor.start_ms && cue.text === exercise.anchor.line_text,
  );
  if (index >= 0) {
    await replayFragment(index);
    return;
  }
  const video = deps.getVideo();
  if (video) {
    video.currentTime = exercise.anchor.start_ms / 1000;
    void video.play().catch(() => undefined);
  }
}

// ---------------------------------------------------------------------------
// Summary and resume
// ---------------------------------------------------------------------------

async function showSummary(): Promise<void> {
  if (!sessionId) return;
  pause();
  const body = openCard(deps.t("study_summary_title", "This session"));
  if (!body) return;
  body.textContent = deps.t("study_loading", "One moment…");
  try {
    await flushProgress(true);
    const summary = await studyCloseSession(sessionId);
    if (!cardEl) return;
    renderSummary(body, summary);
    // Closing ends the session; the next line opens a fresh one.
    sessionId = "";
    syncBar();
    void openSession();
  } catch (error) {
    body.textContent = `⚠ ${(error as Error).message}`;
  }
}

function renderSummary(body: HTMLElement, summary: StudySummary): void {
  body.textContent = "";
  const stats = document.createElement("p");
  stats.className = "av-study-note";
  stats.textContent = [
    `${summary.lines_watched} ${deps.t("study_lines", "lines")}`,
    `${summary.checks_passed}/${summary.checks_asked} ${deps.t("study_checks", "checks")}`,
    `${summary.saved_items} ${deps.t("study_saved", "saved")}`,
  ].join(" · ");
  body.appendChild(stats);

  if (!summary.hardest.length) return;
  const heading = document.createElement("p");
  heading.className = "av-study-note";
  heading.textContent = deps.t("study_hardest", "What gave you trouble");
  const list = document.createElement("ul");
  list.className = "av-study-hardest";
  summary.hardest.forEach((stat) => {
    const item = document.createElement("li");
    const jump = document.createElement("button");
    jump.className = "av-study-jump";
    // Every difficult fragment carries its timecode, so the summary is a list
    // of places to go back to rather than a list of numbers.
    jump.textContent = `${timecode(stat.start_ms)} — ${describeStat(stat.replays, stat.errors)}`;
    jump.addEventListener("click", () => {
      const video = deps.getVideo();
      if (!video) return;
      video.currentTime = stat.start_ms / 1000;
      closeCard();
      resume();
    });
    item.appendChild(jump);
    list.appendChild(item);
  });
  body.append(heading, list);
}

function describeStat(replays: number, errors: number): string {
  const parts = [
    replays ? `${replays}× ${deps.t("study_replayed", "replayed")}` : "",
    errors ? `${errors}× ${deps.t("study_missed", "missed")}` : "",
  ].filter(Boolean);
  return parts.join(", ") || deps.t("study_reviewed", "reviewed");
}

function offerResume(cursorMs: number, linesWatched: number): void {
  const body = openCard(deps.t("study_resume_title", "Pick up where you stopped?"));
  if (!body) return;
  const note = document.createElement("p");
  note.className = "av-study-note";
  note.textContent = `${timecode(cursorMs)} · ${linesWatched} ${deps.t("study_lines", "lines")}`;
  const go = document.createElement("button");
  go.className = "av-study-primary";
  go.textContent = deps.t("study_resume", "Resume");
  go.addEventListener("click", () => {
    const video = deps.getVideo();
    if (video) video.currentTime = cursorMs / 1000;
    closeCard();
    resume();
  });
  body.append(note, go);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toCue(cue: TimedCaptionCue, translated?: TimedCaptionCue): StudyCue {
  return {
    start_ms: Math.max(0, Math.round(cue.startMs)),
    end_ms: Math.max(1, Math.round(cue.endMs)),
    text: cue.text,
    translation: translated?.text ?? "",
  };
}

function timecode(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function studyActive(): boolean {
  return featureEnabled && Boolean(sessionId);
}
