import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { execFileSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = (relativePath) => readFileSync(path.join(root, relativePath), "utf8");

function longestMatchingBlock(left, right) {
  const a = left.replace(/\r\n/g, "\n").split("\n");
  const b = right.replace(/\r\n/g, "\n").split("\n");
  const previous = new Array(b.length + 1).fill(0);
  let longest = 0;
  for (const line of a) {
    const current = new Array(b.length + 1).fill(0);
    for (let index = 0; index < b.length; index += 1) {
      if (line === b[index]) current[index + 1] = previous[index] + 1;
      longest = Math.max(longest, current[index + 1]);
    }
    previous.splice(0, previous.length, ...current);
  }
  return longest;
}

function parseStringCatalogue(body) {
  const entries = {};
  for (const match of body.matchAll(/^\s+"?([a-z0-9_]+)"?:\s*("(?:[^"\\]|\\.)*"),?$/gm)) {
    entries[match[1]] = JSON.parse(match[2]);
  }
  return entries;
}

const CLEAN_ROOM_BASELINE = "2d6393b";

function legacySource(relativePath) {
  return execFileSync("git", ["show", `${CLEAN_ROOM_BASELINE}:veksha-extension/${relativePath}`], {
    cwd: path.resolve(root, ".."),
    encoding: "utf8",
  });
}

test("clean-room replacements share no source block longer than eight lines", () => {
  const popupLayers = [
    "foundation.css", "onboarding.css", "settings-and-lists.css",
    "learning-windows.css", "language-and-billing.css", "workbenches.css",
  ].map((name) => source(`src/popup/styles/${name}`)).join("\n");
  assert.ok(longestMatchingBlock(legacySource("src/popup/popup.css"), popupLayers) <= 8);
  const youtubeRuntime = `${source("src/content/youtube.ts")}\n${source("src/content/youtube-study-runtime.ts")}`;
  assert.ok(longestMatchingBlock(legacySource("src/content/youtube.ts"), youtubeRuntime) <= 8);
  for (const screen of ["SettingsScreen.tsx", "LevelSetupScreen.tsx", "OnboardingScreen.tsx"]) {
    assert.ok(longestMatchingBlock(
      legacySource(`src/popup/screens/${screen}`),
      source(`src/popup/screens/${screen}`),
    ) <= 8, screen);
  }

  assert.equal(existsSync(path.join(root, "src/popup/screens/DebugScreen.tsx")), false);
});

test("the popup has no legacy chat or topic components", () => {
  for (const relativePath of [
    "src/popup/components/ChatInput.tsx",
    "src/popup/components/ChatMessages.tsx",
    "src/popup/screens/TopicsScreen.tsx",
    "src/popup/overlays/TopicPickerOverlay.tsx",
  ]) {
    assert.equal(existsSync(path.join(root, relativePath)), false, relativePath);
  }
});

test("translation is modeled as a workbench, not a conversation", () => {
  const translator = source("src/popup/screens/TranslatorScreen.tsx");
  assert.match(translator, /TranslationSheet/);
  assert.doesNotMatch(translator, /ChatMessage|ChatInput|ChatMessages|msg-user|msg-bot/);
});

test("web-only navigation uses the same current learning surfaces", () => {
  const home = source("src/popup/screens/HomeScreen.tsx");
  assert.match(home, /navigateTo\("myWords"\)/);
  assert.match(home, /navigateTo\("quizlet"\)/);
  assert.doesNotMatch(home, /Translation unavailable\. Try again\./);
});

test("lessons begin from an explicit learning objective", () => {
  const app = source("src/popup/App.tsx");
  const goals = source("src/popup/screens/LearningGoalsScreen.tsx");
  assert.match(app, /LearningGoalsScreen/);
  assert.match(app, /screen === "goals"/);
  assert.match(goals, /lesson_goals_prompt/);
  assert.doesNotMatch(app, /TopicsScreen/);
});

test("removed tutorial assets are not referenced by extension source", () => {
  const trackedEntrypoints = [
    "src/popup/App.tsx",
    "src/content/content.ts",
    "src/background/background.ts",
  ];
  for (const relativePath of trackedEntrypoints) {
    assert.doesNotMatch(source(relativePath), /tut_|Tutorial back|tutorial\.png/i);
  }
});

test("the popup shell is independent from the former tile interface", () => {
  const app = source("src/popup/App.tsx");
  const home = source("src/popup/screens/HomeScreen.tsx");
  const entrypoint = source("src/popup/main.tsx");
  const legacyShell = /shell-(?:main|topbar|content)|screen-home|m-(?:tiles|tile|feature)/;

  assert.match(app, /workspace-frame/);
  assert.match(home, /capability-grid/);
  assert.match(entrypoint, /\.\/styles\/index\.css/);
  assert.doesNotMatch(app, legacyShell);
  assert.doesNotMatch(home, legacyShell);
  assert.equal(existsSync(path.join(root, "src/popup/popup.css")), false);
  assert.match(source("src/popup/styles/index.css"), /foundation\.css/);
  assert.doesNotMatch(source("src/popup/styles/theme.css"), legacyShell);
});

test("Quizlet copy participates in the shared localization catalogue", () => {
  const screen = source("src/popup/screens/QuizletScreen.tsx");
  const strings = source("src/shared/i18n/strings.ts");
  const backendStrings = source("../veksha-backend/i18n.py");

  assert.match(screen, /useT\(\)/);
  assert.match(screen, /t\.quizlet_status_title/);
  assert.match(screen, /t\.quizlet_error_import/);
  assert.doesNotMatch(screen, />\s*(?:Export status|Import from Quizlet|Loading\.\.\.)\s*</);
  for (const key of ["quizlet_loading", "quizlet_export_new", "quizlet_import_title", "quizlet_error_import"]) {
    assert.match(strings, new RegExp(`${key}:`));
    assert.match(backendStrings, new RegExp(`"${key}":`));
  }
});

test("light, colorful, and dark themes are available", () => {
  const runtime = source("src/shared/theme.ts");
  const palette = source("src/shared/palette.css");
  const settings = source("src/popup/screens/SettingsScreen.tsx");

  assert.match(runtime, /\["light", "grove", "dark"\]/);
  assert.match(palette, /data-veksha-theme="grove"/);
  assert.match(settings, /grove: t\.theme_grove/);
});

test("the page assistant boots through the new runtime", () => {
  const entrypoint = source("src/content/content.ts");
  const runtime = source("src/content/page-runtime.ts");
  const overlay = source("src/content/overlay.tsx");

  assert.match(entrypoint, /startPageRuntime/);
  assert.match(entrypoint, /__vekshaPageRuntimeV2/);
  assert.doesNotMatch(entrypoint, /openPopup|runRegionTranslate|showAggressiveReminder/);
  assert.match(runtime, /class PageRuntime/);
  assert.match(runtime, /SelectionAssistant/);
  assert.match(overlay, /vk-page-window/);
  assert.doesNotMatch(overlay, /av-overlay-auto|veksha-overlay-host/);
});

test("translated content stays available while the page scrolls", () => {
  const assistant = source("src/content/selection-assistant.ts");
  const contentStyles = source("src/content/content.css");
  const shellStyles = source("src/popup/styles/shell.css");

  assert.doesNotMatch(assistant, /addEventListener\("scroll", this\.close/);
  assert.match(contentStyles, /\.vk-assistant-card > q[\s\S]*?overflow: hidden auto/);
  assert.match(contentStyles, /\.vk-assistant-result[\s\S]*?overflow: hidden auto/);
  assert.match(shellStyles, /\.capability-card-label[\s\S]*?white-space: normal/);
});

test("retired OCR implementation and coercive reminder code are absent", () => {
  const files = [
    "src/content/content.ts",
    "src/content/page-runtime.ts",
    "src/content/content.css",
    "src/background/background.ts",
    "manifest.json",
    "vite.config.ts",
    "package.json",
    "package-lock.json",
    "scripts/build.mjs",
    "scripts/sync-assets.mjs",
  ];
  for (const relativePath of files) {
    assert.doesNotMatch(source(relativePath), /VEKSHA_OCR|OCR_REGION|tesseract|terror-reminder|runRegionTranslate/i, relativePath);
  }
  for (const relativePath of [
    "src/shared/capture.ts",
    "src/offscreen/offscreen.ts",
    "src/offscreen/offscreen.html",
  ]) {
    assert.equal(existsSync(path.join(root, relativePath)), false, relativePath);
  }
  assert.doesNotMatch(source("manifest.json"), /"offscreen"/);
});

test("full-page focus requires a deliberate session and remains reversible", () => {
  const gate = source("src/focus/main.ts");
  const background = source("src/background/background.ts");
  const settings = source("src/popup/screens/SettingsScreen.tsx");

  assert.match(settings, /startFocusSession/);
  assert.match(settings, /\[20, 40, 60\]/);
  assert.match(background, /sessionBlocksUrl/);
  assert.doesNotMatch(background, /VEKSHA_SHOW_PRACTICE_REMINDER/);
  assert.match(gate, /10 \* 60 \* 1000/);
  assert.match(gate, /STORAGE_KEY_FOCUS_SESSION/);
  assert.doesNotMatch(gate, /mousemove|pointermove|Math\.random/);
});

test("region translation uses a clean capture workspace", () => {
  const background = source("src/background/background.ts");
  const capture = source("src/capture/main.ts");
  const api = source("src/shared/api.ts");

  assert.match(background, /captureVisibleTab/);
  assert.match(background, /VEKSHA_GET_REGION_CAPTURE/);
  assert.match(capture, /translateImageRegion/);
  assert.match(capture, /canvas\.toDataURL/);
  assert.match(api, /\/api\/ocr\/translate-region/);
  assert.doesNotMatch(capture, /tesseract|offscreen/i);
});

test("practice runs through the Adaptive Practice Planner, not a training window", () => {
  const planner = source("src/popup/overlays/PracticePlannerWindow.tsx");
  const app = source("src/popup/App.tsx");
  const overlay = source("src/content/overlay.tsx");
  const strings = source("src/shared/i18n/strings.ts");
  const backendStrings = source("../veksha-backend/i18n.py");

  assert.equal(existsSync(path.join(root, "src/popup/overlays/TrainingWindow.tsx")), false);
  for (const consumer of [app, overlay, source("src/training/index.tsx")]) {
    assert.match(consumer, /PracticePlannerWindow/);
    assert.doesNotMatch(consumer, /TrainingWindow/);
  }

  // The four skills, the four FSRS ratings, and the reason shown to the
  // learner are all part of the surface — not implicit server behaviour.
  assert.match(planner, /practice_skill_recognition|skillName/);
  assert.match(planner, /RATINGS: FsrsRating\[\] = \["again", "hard", "good", "easy"\]/);
  assert.match(planner, /reasonText/);
  assert.match(planner, /type: "commit"/);
  for (const key of [
    "practice_skill_listening",
    "practice_training_skill",
    "practice_rating_easy",
    "practice_why_weakest_skill",
    "practice_summary_limited_by",
  ]) {
    assert.match(strings, new RegExp(`${key}:`));
    assert.match(backendStrings, new RegExp(`"${key}":`));
  }
});

test("Reading Coach fully replaces page immersion", () => {
  const home = source("src/popup/screens/HomeScreen.tsx");
  const runtime = source("src/content/page-runtime.ts");
  const coach = source("src/content/reading-coach.ts");
  const api = source("src/shared/api.ts");

  assert.equal(existsSync(path.join(root, "src/content/immersion.ts")), false);
  assert.equal(existsSync(path.join(root, "src/popup/screens/ImmersionScreen.tsx")), false);
  assert.match(home, /toggleReadingCoach/);
  assert.match(runtime, /initReadingCoach/);
  assert.match(coach, /analyzeReadingCoach/);
  assert.match(coach, /helpReadingParagraph/);
  assert.match(coach, /createReadingQuestion/);
  assert.match(coach, /checkReadingAnswer/);
  assert.match(runtime, /refreshReadingCoach/);
  assert.doesNotMatch(`${home}\n${runtime}\n${api}`, /analyzeImmersion|TOGGLE_IMMERSION|Icons\.immersion/);
});

test("Reading Sessions replace passive browsing observation", () => {
  const runtime = source("src/content/page-runtime.ts");
  const reader = source("src/content/reading-session.ts");
  const words = source("src/popup/screens/MyWordsScreen.tsx");
  const styles = source("src/popup/styles/settings-and-lists.css");
  assert.match(words, /startReadingSession/);
  assert.match(words, /endReadingSession/);
  assert.match(reader, /sessionId/);
  assert.match(runtime, /VEKSHA_READING_SESSION_CHANGED/);
  assert.match(styles, /\.my-words-screen\s*\{[\s\S]*?overflow-y: auto/);
  assert.match(styles, /\.my-words-list\s*\{[\s\S]*?flex: 0 0 auto[\s\S]*?overflow: visible/);
  assert.doesNotMatch(`${runtime}\n${reader}\n${words}`, /TOGGLE_VOCAB|vocabfreq/i);
});

test("Pattern Workshop saves only after a micro-practice", () => {
  const workshop = source("src/content/pattern-workshop.ts");
  const api = source("src/shared/api.ts");
  const home = source("src/popup/screens/HomeScreen.tsx");
  assert.match(workshop, /completePatternWorkshop/);
  assert.match(workshop, /pattern_workshop_choose/);
  assert.match(api, /\/api\/pattern-workshop\/complete/);
  assert.match(api, /\/api\/pattern-workshop\/error-drafts/);
  assert.doesNotMatch(home, /TOGGLE_GRAMMAR|GRAMMAR_LENS/);
});

test("localization uses bundled static catalogues", () => {
  const runtime = source("src/shared/i18n/index.tsx");
  const catalogs = source("src/shared/i18n/catalogs.ts");
  assert.match(runtime, /catalogFor/);
  assert.match(catalogs, /i18n_ru\.json/);
  assert.doesNotMatch(runtime, /fetch\(|\/api\/i18n\/translate|fillMissingKeys/);
  assert.match(source("src/shared/languages.ts"), /Intl\.DisplayNames/);
  assert.match(source("src/shared/i18n/locales.ts"), /normalizeUiLocale/);
  assert.doesNotMatch(source("src/popup/screens/NativeLangScreen.tsx"), /switchLanguage/);
});

test("the extension English catalogue exactly matches the canonical backend source", () => {
  const extensionSource = source("src/shared/i18n/strings.ts");
  const backendSource = source("../veksha-backend/i18n.py");
  const extensionBody = extensionSource.match(/export const EN = \{([\s\S]*?)\n\} satisfies Record<string, string>;/)?.[1];
  const backendBody = backendSource.match(/UI_STRINGS: dict\[str, str\] = \{([\s\S]*?)\n\}/)?.[1];
  assert.ok(extensionBody, "extension EN catalogue");
  assert.ok(backendBody, "backend UI_STRINGS catalogue");
  assert.deepEqual(parseStringCatalogue(extensionBody), parseStringCatalogue(backendBody));
});

test("dynamic localization does not reintroduce English fragments", () => {
  const goals = source("src/popup/screens/LearningGoalsScreen.tsx");
  const reminder = source("src/popup/overlays/ReminderCard.tsx");
  assert.match(goals, /getLanguageName\(currentSettings\.target_lang, lang\)/);
  assert.match(goals, /getScriptName\(writing\.script, lang, writing\.script_name\)/);
  assert.match(goals, /kind === "latin_extended"[\s\S]*?literacy_course_latin_desc/);
  assert.match(reminder, /Intl\.ListFormat\(locale/);
  assert.match(reminder, /t\.reminder_kicker/);
  assert.doesNotMatch(reminder, /join\(" and "\)|VEKSHA \/ PRACTICE/);
});

test("bundled catalogues stay in sync with the reviewed sources", () => {
  const reviewedDirectory = path.join(root, "..", "veksha-backend", "data");
  for (const name of readdirSync(reviewedDirectory).filter((entry) => /^i18n_[a-z-]+\.json$/.test(entry))) {
    assert.equal(
      source(`src/shared/i18n/catalogs/${name}`),
      readFileSync(path.join(reviewedDirectory, name), "utf8"),
      name,
    );
  }
  assert.equal(
    source("src/shared/i18n/ui_locales.json"),
    readFileSync(path.join(reviewedDirectory, "ui_locales.json"), "utf8"),
  );
});

test("container builds include or safely reuse localization inputs", () => {
  const webDockerfile = readFileSync(path.join(root, "..", "veksha-web", "Dockerfile"), "utf8");
  const syncScript = source("scripts/sync-i18n.mjs");
  assert.match(webDockerfile, /COPY veksha-extension\/scripts\/sync-i18n\.mjs/);
  assert.match(webDockerfile, /COPY veksha-backend\/data\/i18n_\*\.json/);
  assert.match(syncScript, /if \(!existsSync\(reviewedDir\)\)/);
});
