import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = (relativePath) => readFileSync(path.join(root, relativePath), "utf8");

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
  assert.match(entrypoint, /\.\/shell\.css/);
  assert.doesNotMatch(app, legacyShell);
  assert.doesNotMatch(home, legacyShell);
  assert.doesNotMatch(source("src/popup/popup.css"), legacyShell);
  assert.doesNotMatch(source("src/popup/theme.css"), legacyShell);
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
