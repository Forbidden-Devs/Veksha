export type Screen = "onboarding" | "chat" | "topics" | "settings" | "statistics" | "debug";
export type Overlay = "training" | "reminder" | null;
export type SettingsMode = "onboarding" | "menu";

export interface ChatMessage {
  id: string;
  text: string;
  role: "user" | "bot" | "error";
  time: Date;
  isTranslation?: boolean;
  originalText?: string;
  speechLang?: string;
}

export interface MessageResponse {
  messages: string[];
}

export interface TranslateResponse {
  translation: string;
  detected_source_lang: string | null;
  single: boolean;
  normalized_text: string;
}

export interface SettingsData {
  english_level: string | null;
  goals: string;
  general_prompt: string;
  native_lang: string;
  target_lang: string;
  reminder_level: number;
  overseer: boolean;
  is_onboarded: boolean;
}

export interface RemindersData {
  due_words: number;
  due_word_names: string[];
  due_topic: string | null;
  should_remind: boolean;
  poll_interval_minutes: number;
}

export interface KBSummaryData {
  learning_count: number;
  known_count: number;
  topics_count: number;
}

// ---------------------------------------------------------------------------
// Training window
// ---------------------------------------------------------------------------

export type TaskType = "translation" | "synonym" | "example" | "reverse_translation";

export type TrainingOutcome = "correct" | "incorrect" | "vague" | "garbage";

export interface TrainingTask {
  task_id: string;
  word: string;
  context: string;
  task_type: TaskType;
  question: string;
  reverse_text?: string;
  counter?: number;
}

export interface TrainingResult {
  task_id: string;
  outcome: TrainingOutcome;
  feedback: string;
}

// ---------------------------------------------------------------------------
// Lesson window (topic-based learning)
// ---------------------------------------------------------------------------

export interface ContentSection {
  icon?: string;
  header: string;
  items?: string[];
  text?: string;
  highlight: boolean;
}

export interface BlockContent {
  title: string;
  intro: string;
  sections: ContentSection[];
}

export interface LessonBlock {
  name: string;
  content: BlockContent;
}

export interface WordEntry {
  name: string;
  context: string;
  counter: number;
  known: boolean;
  next_review: number;
}

export interface LessonTopicSummary {
  name: string;
  block_count: number;
  mastery: number;
  last_reviewed: number | null;
}

export interface LessonQuestion {
  question_id: string;
  block_name: string;
  question: string;
}
