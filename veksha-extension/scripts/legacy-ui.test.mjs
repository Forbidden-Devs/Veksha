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
