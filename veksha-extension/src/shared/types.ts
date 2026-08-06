export type Screen = "home" | "translator" | "goals" | "dictionary" | "myWords" | "settings" | "subscription" | "statistics" | "debug" | "quizlet";
export type Overlay = "training" | "reminder" | null;
export type SettingsMode = "onboarding" | "menu";

export interface TranslateResponse {
  translation: string;
  detected_source_lang: string | null;
  single: boolean;
  normalized_text: string;
  vocabulary_mode?: "saved" | "suggested";
}

export interface SettingsData {
  /** User-facing name (editable); the `username` account id is internal. */
  display_name?: string;
  english_level: string | null;
  goals: string;
  general_prompt: string;
  native_lang: string;
  target_lang: string;
  target_langs?: string[];
  language_settings?: Record<string, LanguageSettings>;
  reminder_level: number;
  overseer: boolean;
  mining_same_level_examples: number;
  mining_higher_level_examples: number;
  is_onboarded: boolean;
}

export interface LanguageSettings {
  level: string;
  goals: string;
  prompt: string;
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
  anki_reviews: number;
  training_reviews: number;
}

// ---------------------------------------------------------------------------
// Adaptive Practice Planner
// ---------------------------------------------------------------------------

/** The four skills tracked separately for every lexical sense. */
export type PracticeSkill =
  | "recognition"
  | "recall"
  | "contextual_meaning"
  | "listening";

export type TaskType =
  | "translation" | "synonym" | "multiple_choice"
  | "reverse_translation" | "cloze" | "word_bank"
  | "context_meaning" | "usage_example" | "sense_choice"
  | "listening_recall" | "listening_cloze" | "listening_choice";

/** "core" is the planned task; the others are steps of a corrective chain. */
export type TaskStage = "core" | "support" | "transfer";

export type PracticeReasonCode =
  | "new_word"
  | "recent_error"
  | "weakest_skill"
  | "due_review"
  | "skill_rotation"
  | "correction_support"
  | "correction_transfer";

export type FsrsRating = "again" | "hard" | "good" | "easy";

export type TrainingOutcome = "correct" | "incorrect" | "vague" | "garbage";

export interface PracticeReason {
  code: PracticeReasonCode;
  skill: PracticeSkill;
}

export interface SkillProgress {
  skill: PracticeSkill;
  confidence: number;
  attempts: number;
}

export interface TrainingTask {
  task_id: string;
  item_id: string;
  task_kind: TaskType;
  skill: PracticeSkill;
  stage: TaskStage;
  question: string;
  /** Non-empty only for the option-based formats. */
  options: string[];
  /** Learning-language text the client speaks for listening tasks. */
  audio_text: string;
  hint: string;
  counter?: number;
  reason: PracticeReason;
  is_correction: boolean;
}

export interface TrainingResult {
  task_id: string;
  outcome: TrainingOutcome;
  feedback: string;
  error_note: string;
  /** Null when the input was not an answer at all — nothing to schedule. */
  suggested_rating: FsrsRating | null;
  /** Sent once the learner has answered and only when they missed. */
  expected_answer: string;
}

export interface TrainingCommitted {
  task_id: string;
  rating: FsrsRating;
  counts_as_review: boolean;
  correction: { stage: TaskStage; skill: PracticeSkill } | null;
  skills: SkillProgress[];
  progress: { done: number; target: number };
}

export interface SessionItemReport {
  item_id: string;
  term: string;
  consolidated: boolean;
  limiting_skill: PracticeSkill;
  limiting_confidence: number;
}

export interface SessionSummary {
  reviewed: number;
  corrections: number;
  skills: { skill: PracticeSkill; count: number }[];
  items: SessionItemReport[];
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
  item_id: string;
  name: string;
  context: string;
  translation: string;
  transcription: string;
  counter: number;
  known: boolean;
  next_review: number;
  added_at: number;
  sentence_mining?: SentenceMiningCard | null;
}

export interface SentenceMiningExample {
  sentence: string;
  translation: string;
  level: string;
  is_higher: boolean;
}

export interface SentenceMiningCollocation {
  text: string;
  translation: string;
}

export interface SentenceMiningCard {
  examples: SentenceMiningExample[];
  mnemonic: string;
  collocations: SentenceMiningCollocation[];
  config: Record<string, string | number>;
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
