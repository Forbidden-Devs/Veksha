export type Screen = "home" | "translator" | "goals" | "dictionary" | "myWords" | "settings" | "subscription" | "statistics" | "quizlet";
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
  mining_same_level_examples: number;
  mining_higher_level_examples: number;
  is_onboarded: boolean;
  writing_system?: WritingSystemProfile | null;
}

export interface LanguageSettings {
  level: string;
  goals: string;
  prompt: string;
  literacy_stage?: LiteracyStage;
}

export type LiteracyStage = "not_started" | "learning" | "mastered";
export type TranscriptionMode = "always" | "on_demand" | "standard";

export interface WritingSystemProfile {
  kind: "standard" | "latin_extended" | "script_variant" | "new_alphabet" | "unsupported";
  script: string;
  script_name: string;
  literacy_stage: LiteracyStage;
  transcription_mode: TranscriptionMode;
  course_available: boolean;
}

export interface RemindersData {
  due_words: number;
  due_word_names: string[];
  due_goal: string | null;
  should_remind: boolean;
  poll_interval_minutes: number;
}

export interface KBSummaryData {
  learning_count: number;
  known_count: number;
  goals_count: number;
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
// Goal-oriented lessons
// ---------------------------------------------------------------------------

export type ContentSection = {
  header: string;
  highlight: boolean;
  text?: string;
  items?: string[];
  icon?: string;
};

export interface StepMaterial {
  title: string;
  intro: string;
  sections: ContentSection[];
}

/** Why an answer went the way it did — what the next step is aimed at. */
export type DifficultyCause =
  | "unknown_term"
  | "missed_signal"
  | "rule_not_applied"
  | "lucky_guess"
  | "explains_not_produces"
  | "transfers_confidently"
  | "unclear";

export type ActivityKind =
  | "find_in_material"
  | "explain_example"
  | "compare_forms"
  | "correct_error"
  | "predict_continuation"
  | "paraphrase"
  | "create_example"
  | "role_reply"
  | "apply_unaided";

export type CriterionStatus = "untested" | "gap" | "emerging" | "implied" | "met";

export interface CriterionView {
  criterion_id: string;
  statement: string;
  depth: number;
  status: CriterionStatus;
  attempts: number;
  cause: DifficultyCause | null;
}

export interface GoalStep {
  step_id: string;
  criterion_id: string;
  criterion: string;
  activity: ActivityKind;
  reason: string;
  material: StepMaterial;
  question: string;
}

export interface GoalSummaryEntry {
  criterion_id: string;
  statement: string;
  status: CriterionStatus;
  attempts: number;
  cause: DifficultyCause | null;
}

export interface GoalReport {
  achieved: boolean;
  stopped_on_time: boolean;
  narrative: string;
  next_goal: string;
  proven: GoalSummaryEntry[];
  shaky: GoalSummaryEntry[];
  examples: string[];
  terms: { term: string; translation: string }[];
  patterns: { label: string; category: string; example: string }[];
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

export interface LearningGoalSummary {
  goal_id: string;
  statement: string;
  framed: boolean;
  achieved: boolean;
  progress: number;
  minutes: number;
  spent_seconds: number;
  has_material: boolean;
  criteria: CriterionView[];
  last_worked_at: number | null;
  kind: "standard" | "alphabet";
}
