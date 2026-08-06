/**
 * strings.ts — single source of truth for all UI strings in the extension.
 * Mirror of: veksha-backend/i18n.py → UI_STRINGS (keys must match).
 *
 * EN — base English object, used as fallback for any language.
 */

export interface Strings {
  // Common
  app_loading: string;
  feature_enabled: string;
  feature_disabled: string;
  feature_blocked: string;
  common_yes: string;
  common_no: string;
  ai_block_title: string;
  ai_block_enabled: string;
  ai_block_disable_page: string;
  ai_block_disable_site: string;
  ai_block_enable_page: string;
  ai_block_enable_site: string;
  ai_block_dialog_hint: string;
  ai_block_settings_hint: string;
  ai_block_settings_title: string;
  ai_block_settings_desc: string;
  ai_block_add_placeholder: string;
  ai_block_add: string;
  ai_block_remove: string;
  ai_block_empty: string;
  ai_block_invalid: string;
  // Native language picker (step 1 of onboarding)
  native_lang_title: string;
  native_lang_subtitle: string;
  // Target language picker (step 3 of onboarding)
  target_lang_title: string;
  target_lang_subtitle: string;
  target_lang_start: string;
  language_search_no_results: string;
  // Onboarding
  onboarding_title: string;
  onboarding_subtitle: string;
  onboarding_name_placeholder: string;
  onboarding_continue: string;
  onboarding_loading: string;
  onboarding_err_empty: string;
  onboarding_err_long: string;
  onboarding_err_taken: string;
  onboarding_or: string;
  onboarding_google: string;
  onboarding_google_err: string;
  // Menu
  menu_title: string;
  menu_learn: string;
  menu_training: string;
  menu_statistics: string;
  menu_settings: string;
  menu_debug: string;
  translator_title: string;
  reminder_label: string;
  translator_source_label: string;
  translator_source_placeholder: string;
  translator_action: string;
  translator_working: string;
  translator_clear: string;
  translator_result_label: string;
  translator_listen: string;
  translator_explain: string;
  translator_note_label: string;
  translator_failed: string;
  translator_explain_failed: string;
  ci_meter_on: string;
  ci_meter_off: string;
  ci_meter_loading: string;
  ci_meter_refine: string;
  ci_meter_badge_known: string;
  ci_meter_verdict_ideal: string;
  ci_meter_verdict_too_easy: string;
  ci_meter_verdict_too_hard: string;
  ci_meter_verdict_close: string;
  reading_coach_projection: string;
  reading_coach_obstacles: string;
  reading_coach_learning: string;
  reading_coach_inbox: string;
  reading_coach_prepare: string;
  reading_coach_preparing: string;
  reading_coach_added: string;
  reading_coach_failed: string;
  reading_coach_ready: string;
  reading_coach_structure: string;
  reading_coach_selected_title: string;
  reading_coach_selected_hint: string;
  reading_coach_help_paragraph: string;
  reading_coach_check_understanding: string;
  reading_coach_select_paragraph: string;
  reading_coach_working: string;
  reading_coach_reveal_translation: string;
  reading_coach_hide_translation: string;
  reading_coach_advanced_unavailable: string;
  reading_coach_answer_placeholder: string;
  reading_coach_check_answer: string;
  reading_coach_question_expired: string;
  feature_guide_open: string;
  feature_guide_close: string;
  reading_coach_guide_title: string;
  reading_coach_guide_intro: string;
  reading_coach_guide_step_1: string;
  reading_coach_guide_step_2: string;
  reading_coach_guide_step_3: string;
  reading_coach_guide_tip: string;
  dual_subtitles_guide_title: string;
  dual_subtitles_guide_intro: string;
  dual_subtitles_guide_step_1: string;
  dual_subtitles_guide_step_2: string;
  dual_subtitles_guide_step_3: string;
  dual_subtitles_guide_tip: string;
  grammar_memory_title: string;
  grammar_memory_on: string;
  grammar_memory_off: string;
  grammar_memory_scanning: string;
  grammar_memory_disable: string;
  grammar_memory_collapse: string;
  grammar_memory_expand: string;
  grammar_hint_select: string;
  grammar_analyze_selection: string;
  grammar_analysis_loading: string;
  grammar_analysis_failed: string;
  grammar_analysis_empty: string;
  grammar_roles_title: string;
  grammar_patterns_title: string;
  grammar_memory_patterns: string;
  grammar_memory_loading: string;
  grammar_memory_empty: string;
  grammar_memory_seen: string;
  grammar_memory_mastered: string;
  grammar_memory_reopen: string;
  grammar_memory_guide_title: string;
  grammar_memory_guide_intro: string;
  grammar_memory_guide_step_1: string;
  grammar_memory_guide_step_2: string;
  grammar_memory_guide_step_3: string;
  grammar_memory_guide_tip: string;
  grammar_role_subject: string;
  grammar_role_verb: string;
  grammar_role_object: string;
  grammar_role_place: string;
  grammar_role_time: string;
  grammar_role_modifier: string;
  my_words_title: string;
  my_words_intro: string;
  my_words_on: string;
  my_words_off: string;
  my_words_empty: string;
  my_words_known: string;
  my_words_unknown: string;
  my_words_seen_on: string;
  my_words_add: string;
  my_words_added: string;
  my_words_add_error: string;
  vocabulary_inbox_title: string;
  vocabulary_inbox_empty: string;
  vocabulary_inbox_seen: string;
  vocabulary_inbox_learn: string;
  vocabulary_inbox_known: string;
  vocabulary_inbox_ignore: string;
  vocabulary_inbox_error: string;
  my_words_guide_step_1: string;
  my_words_guide_step_2: string;
  my_words_guide_step_3: string;
  my_words_guide_tip: string;
  // Settings
  settings_title: string;
  settings_intro: string;
  settings_theme: string;
  theme_light: string;
  theme_grove: string;
  theme_dark: string;
  settings_display_name: string;
  settings_native_lang: string;
  settings_learning_languages: string;
  settings_add_language: string;
  settings_remove_language: string;
  settings_target_lang: string;
  settings_level: string;
  settings_level_placeholder: string;
  settings_goals: string;
  settings_goals_placeholder: string;
  settings_prompt_label: string;
  settings_prompt_placeholder: string;
  settings_mining_title: string;
  settings_mining_desc: string;
  settings_mining_current: string;
  settings_mining_higher: string;
  settings_reminder_level: string;
  settings_reminder_level_desc: string;
  settings_reminder_level_1: string;
  settings_reminder_level_2: string;
  settings_reminder_level_3: string;
  settings_persistent: string;
  settings_persistent_desc: string;
  settings_focus_guard: string;
  settings_focus_guard_desc: string;
  settings_dual_subtitles: string;
  settings_dual_subtitles_desc: string;
  settings_subscription: string;
  settings_sub_free: string;
  settings_sub_premium: string;
  settings_sub_premium_active: string;
  settings_sub_desc: string;
  settings_sub_connect: string;
  settings_sub_manage: string;
  settings_sub_err: string;
  settings_promo_label: string;
  settings_promo_placeholder: string;
  settings_promo_submit: string;
  settings_promo_success: string;
  settings_promo_error_invalid: string;
  settings_promo_error_exhausted: string;
  settings_promo_error_already_redeemed: string;
  settings_promo_error_generic: string;
  premium_required_title: string;
  premium_required_desc: string;
  subscription_title: string;
  subscription_intro_new: string;
  subscription_intro_manage: string;
  subscription_intro_add: string;
  subscription_grammar_desc: string;
  subscription_monthly: string;
  subscription_total: string;
  subscription_continue: string;
  subscription_opened: string;
  subscription_empty: string;
  subscription_load_error: string;
  subscription_cancel: string;
  subscription_cancel_confirm: string;
  subscription_cancel_error: string;
  settings_account: string;
  settings_google_link: string;
  settings_google_linked: string;
  settings_google_link_taken: string;
  settings_signout: string;
  settings_signout_confirm: string;
  settings_save: string;
  settings_saving: string;
  settings_translating: string;
  settings_err_no_level: string;
  settings_err_same_lang: string;
  settings_err_load: string;
  settings_err_save: string;
  // English levels
  level_beginner: string;
  level_elementary: string;
  level_intermediate: string;
  level_upper_intermediate: string;
  level_advanced: string;
  // Statistics
  stats_title: string;
  stats_in_progress: string;
  stats_known: string;
  stats_topics: string;
  stats_ready: string;
  stats_anki_reviews: string;
  stats_training_reviews: string;
  stats_badge_new: string;
  stats_badge_known: string;
  stats_vocabulary: string;
  dictionary_title: string;
  dictionary_cards: string;
  dictionary_search_placeholder: string;
  dictionary_sort_label: string;
  dictionary_sort_az: string;
  dictionary_sort_za: string;
  dictionary_sort_newest: string;
  dictionary_sort_oldest: string;
  dictionary_no_results: string;
  dictionary_translation: string;
  dictionary_transcription: string;
  dictionary_show_answer: string;
  dictionary_again: string;
  dictionary_good: string;
  sentence_mining_title: string;
  sentence_mining_loading: string;
  sentence_mining_examples: string;
  sentence_mining_mnemonic: string;
  sentence_mining_collocations: string;
  sentence_mining_regenerate: string;
  sentence_mining_error: string;
  sentence_mining_level_up: string;
  stats_review_today: string;
  stats_review_in_days: string;
  stats_review_overdue: string;
  // Reminders
  reminder_title: string;
  reminder_subtitle_default: string;
  reminder_words: string;    // placeholder: {n}
  reminder_topic: string;
  reminder_have: string;     // placeholder: {items}
  reminder_start: string;
  reminder_dismiss: string;
  reminder_focus_note: string;
  reminder_snooze: string;
  reminder_skip_today: string;
  // Adaptive Practice Planner
  training_title: string;
  training_loading: string;
  training_done: string;     // placeholder: {n}
  training_empty: string;
  training_close: string;
  training_check: string;
  training_checking: string;
  training_next: string;
  training_placeholder: string;
  training_new_word: string;
  training_already_know: string;
  training_err_connect: string;
  training_err_lost: string;
  training_err_server: string;
  practice_title: string;
  practice_planning: string;
  // The four skills tracked per lexical sense
  practice_skill_recognition: string;
  practice_skill_recall: string;
  practice_skill_contextual_meaning: string;
  practice_skill_listening: string;
  practice_training_skill: string;   // placeholder: {skill}
  // Why the planner chose this exercise
  practice_why_new_word: string;             // placeholder: {skill}
  practice_why_recent_error: string;         // placeholder: {skill}
  practice_why_weakest_skill: string;        // placeholder: {skill}
  practice_why_due_review: string;           // placeholder: {skill}
  practice_why_skill_rotation: string;       // placeholder: {skill}
  practice_why_correction_support: string;   // placeholder: {skill}
  practice_why_correction_transfer: string;  // placeholder: {skill}
  practice_stage_support: string;
  practice_stage_transfer: string;
  practice_expected_answer: string;
  practice_show_hint: string;
  practice_replay: string;
  // The four FSRS ratings
  practice_rating_label: string;
  practice_rating_again: string;
  practice_rating_hard: string;
  practice_rating_good: string;
  practice_rating_easy: string;
  practice_rating_suggested: string;  // placeholder: {rating}
  practice_summary_corrections: string;   // placeholder: {n}
  practice_summary_consolidated: string;
  practice_summary_needs_work: string;
  practice_summary_limited_by: string;    // placeholder: {skill}
  // Goal-oriented lesson window
  lesson_framing: string;
  lesson_loading_step: string;
  lesson_err_connect: string;
  lesson_err_lost: string;
  lesson_err_server: string;
  lesson_err_no_goal: string;
  lesson_resumed: string;
  lesson_criteria_title: string;
  lesson_criteria_done: string;   // placeholders: {n}, {total}
  lesson_time_left: string;       // placeholder: {n}
  lesson_practice_hint: string;
  lesson_finish_early: string;
  lesson_next_step: string;
  // Criterion status chips
  lesson_status_untested: string;
  lesson_status_gap: string;
  lesson_status_emerging: string;
  lesson_status_implied: string;
  lesson_status_met: string;
  // What this step is asking for
  lesson_activity_find_in_material: string;
  lesson_activity_explain_example: string;
  lesson_activity_compare_forms: string;
  lesson_activity_correct_error: string;
  lesson_activity_predict_continuation: string;
  lesson_activity_paraphrase: string;
  lesson_activity_create_example: string;
  lesson_activity_role_reply: string;
  lesson_activity_apply_unaided: string;
  // Why the answer went the way it did
  lesson_cause_unknown_term: string;
  lesson_cause_missed_signal: string;
  lesson_cause_rule_not_applied: string;
  lesson_cause_lucky_guess: string;
  lesson_cause_explains_not_produces: string;
  lesson_cause_transfers_confidently: string;
  // Closing report
  lesson_summary_achieved: string;
  lesson_summary_out_of_time: string;
  lesson_summary_stopped: string;
  lesson_summary_proven: string;
  lesson_summary_shaky: string;
  lesson_summary_examples: string;
  lesson_summary_next_goal: string;
  lesson_summary_new_words: string;
  lesson_summary_new_patterns: string;
  dictionary_empty: string;
  // Quizlet import/export
  quizlet_loading: string;
  quizlet_status_title: string;
  quizlet_total_words: string;
  quizlet_exported: string;
  quizlet_not_exported: string;
  quizlet_export_options: string;
  quizlet_exporting: string;
  quizlet_export_new: string;
  quizlet_export_all: string;
  quizlet_export_new_hint: string;
  quizlet_export_all_hint: string;
  quizlet_format_hint: string;
  quizlet_import_title: string;
  quizlet_import_desc: string;
  quizlet_importing: string;
  quizlet_select_csv: string;
  quizlet_imported: string;
  quizlet_skipped: string;
  quizlet_errors: string;
  quizlet_export_success: string;
  quizlet_export_steps_title: string;
  quizlet_export_step_1: string;
  quizlet_export_step_2: string;
  quizlet_export_step_3: string;
  quizlet_export_step_4: string;
  quizlet_error_status: string;
  quizlet_error_export: string;
  quizlet_error_export_all: string;
  quizlet_error_csv: string;
  quizlet_error_import: string;
  lesson_goals_kicker: string;
  lesson_goals_prompt: string;
  lesson_goals_hint: string;
  lesson_goals_placeholder: string;
  lesson_goals_material_toggle: string;
  lesson_goals_material_placeholder: string;
  lesson_goals_minutes: string;
  lesson_goals_start: string;
  lesson_goals_active: string;
  lesson_goals_loading: string;
  lesson_goals_evidence: string;
  lesson_goals_continue: string;
  lesson_goals_empty: string;
  lesson_goals_load_failed: string;
  lesson_goals_create_failed: string;
  // Shared copy retained by setup and the web home screen.
  common_back: string;
  home_translation_body: string;
  home_quick_saved: string;
  home_quick_suggested: string;
  home_hero_title: string;
  // Immersion explainer modal (shown on enable until "I already know")
  // App shell (sidebar + topbar)
  nav_topics: string;
  nav_training: string;
  nav_stats: string;
  nav_settings: string;
  topbar_train: string;
  sub_topics: string;
  sub_stats: string;
  sub_settings: string;
  sidebar_collected: string;  // placeholder: {n}
  // PDF area translate (OCR)
  pdf_translate_region: string;
  pdf_region_hint: string;
  pdf_no_text: string;
  pdf_patch_dismiss: string;
  ocr_capture_hint: string;
  ocr_recognized_text: string;
  ocr_translate_selection: string;
  ocr_choose_again: string;
  ocr_translate_area: string;
  ocr_copy_translation: string;
  ocr_translation_copied: string;
  // Content script (translation popup on page)
  content_translating: string;
  content_translate: string;
  content_close: string;
  content_translation_failed: string;
  content_explanation_failed: string;
  content_explain: string;
  content_listen: string;
  content_breakdown: string;
  content_edit_text: string;
  content_hide_source: string;
  content_no_user: string;
  content_dualsubs: string;
  // Level setup (step 4 of onboarding)
  level_setup_title: string;
  level_setup_subtitle: string;
  level_setup_optional: string;
  // Debug
  debug_title: string;
  debug_user: string;
  debug_backend: string;
  debug_browser_lang: string;
  debug_all_langs: string;
  debug_commands: string;
  debug_simulate_training_name: string;
  debug_simulate_training_desc: string;
  debug_advance_day_name: string;
  debug_advance_day_desc: string;
  debug_reset_name: string;
  debug_reset_desc: string;
  debug_reset_confirm: string;  // placeholder: {username}
  debug_regen_name: string;
  debug_regen_desc: string;
  debug_regen_done: string;
  debug_run: string;
  debug_reloading: string;
}

export const EN: Strings = {
  app_loading: "Loading...",
  feature_enabled: "On",
  feature_disabled: "Off",
  feature_blocked: "Blocked",
  common_yes: "Yes",
  common_no: "No",
  ai_block_title: "Disable AI features",
  ai_block_enabled: "Active here",
  ai_block_disable_page: "Disable on this page",
  ai_block_disable_site: "Disable on this entire site",
  ai_block_enable_page: "Enable on this page",
  ai_block_enable_site: "Enable on this entire site",
  ai_block_dialog_hint: "You can always review and edit the full blocklist in Settings.",
  ai_block_settings_hint: "The full list of blocked sites is always available in Settings.",
  ai_block_settings_title: "AI feature blocklist",
  ai_block_settings_desc: "Veksha AI tools will stay inactive on these sites and pages.",
  ai_block_add_placeholder: "example.com",
  ai_block_add: "Add site",
  ai_block_remove: "Remove",
  ai_block_empty: "No sites or pages are blocked yet.",
  ai_block_invalid: "Enter a valid site address.",
  native_lang_title: "What's your language?",
  native_lang_subtitle: "We'll show translations and the interface in your language",
  target_lang_title: "What do you want to learn?",
  target_lang_subtitle: "Choose one or more languages you want to study",
  target_lang_start: "Let's start!",
  language_search_no_results: "No languages found. Try another name.",
  onboarding_title: "And what's your name?",
  onboarding_subtitle: "Pick a name to keep your vocabulary and progress. You can change it later in Settings.",
  onboarding_name_placeholder: "Your name",
  onboarding_continue: "Continue",
  onboarding_loading: "Loading...",
  onboarding_err_empty: "Please enter a name.",
  onboarding_err_long: "Name is too long.",
  onboarding_err_taken: "This name is already taken.",
  onboarding_or: "or",
  onboarding_google: "Continue with Google",
  onboarding_google_err: "Google sign-in failed. Try again.",
  menu_title: "Menu",
  menu_learn: "Start learning",
  menu_training: "Training",
  menu_statistics: "Statistics",
  menu_settings: "Settings",
  menu_debug: "Debug",
  translator_title: "Translation desk",
  reminder_label: "Review queue",
  translator_source_label: "Text to work with",
  translator_source_placeholder: "Paste a word, sentence, or short passage",
  translator_action: "Translate text",
  translator_working: "Working…",
  translator_clear: "Clear",
  translator_result_label: "Translation",
  translator_listen: "Play audio",
  translator_explain: "Explain choices",
  translator_note_label: "Language note",
  translator_failed: "Translation is temporarily unavailable.",
  translator_explain_failed: "The translation is ready, but its explanation could not be loaded.",
  ci_meter_on: "Reading Coach on",
  ci_meter_off: "Reading Coach",
  ci_meter_loading: "Checking readability…",
  ci_meter_refine: "Refine with AI",
  ci_meter_badge_known: "{pct}% known · {cefr}",
  ci_meter_verdict_ideal: "Great i+1 content for you — mostly familiar with a healthy stretch of new words.",
  ci_meter_verdict_too_easy: "You know this well already — good for fluency practice, but little new vocabulary.",
  ci_meter_verdict_too_hard: "This may be too difficult right now — expect to look up a lot of words.",
  ci_meter_verdict_close: "Close to your level.",
  reading_coach_projection: "Learn these words: {before}% → {after}% coverage",
  reading_coach_obstacles: "Words blocking this page",
  reading_coach_learning: "learning",
  reading_coach_inbox: "in inbox",
  reading_coach_prepare: "Prepare selected words",
  reading_coach_preparing: "Preparing…",
  reading_coach_added: "{n} word(s) added to your Inbox",
  reading_coach_failed: "Could not prepare words",
  reading_coach_ready: "No high-impact blockers found. Start reading!",
  reading_coach_structure: "Vocabulary {lexical} · sentence structure {structure} · {average} words/sentence",
  reading_coach_selected_title: "Selected paragraph",
  reading_coach_selected_hint: "Select a paragraph on the page, then ask for a hint or check your understanding.",
  reading_coach_help_paragraph: "Help me understand",
  reading_coach_check_understanding: "Check understanding",
  reading_coach_select_paragraph: "Select a complete paragraph first.",
  reading_coach_working: "Preparing…",
  reading_coach_reveal_translation: "Reveal translation",
  reading_coach_hide_translation: "Hide translation",
  reading_coach_advanced_unavailable: "This advanced Reading Coach tool requires activation or is temporarily unavailable.",
  reading_coach_answer_placeholder: "Answer in your own words",
  reading_coach_check_answer: "Check answer",
  reading_coach_question_expired: "This question expired. Create a new one.",
  feature_guide_open: "How it works",
  feature_guide_close: "Got it",
  reading_coach_guide_title: "How Reading Coach works",
  reading_coach_guide_intro: "Reading Coach checks a page against the words you know and helps you prepare before you start reading.",
  reading_coach_guide_step_1: "Open an article in the language you're learning, then turn on Reading Coach from Veksha.",
  reading_coach_guide_step_2: "Open the page badge to see your current coverage, the most important unfamiliar words, and the projected coverage after learning them.",
  reading_coach_guide_step_3: "Select the useful blockers and prepare them. Veksha adds enriched suggestions to your Vocabulary Inbox for review.",
  reading_coach_guide_tip: "Words already being learned or waiting in your Inbox are marked and won't be added twice.",
  dual_subtitles_guide_title: "How dual subtitles work",
  dual_subtitles_guide_intro: "Dual subtitles add a translation above the original captions while you watch YouTube.",
  dual_subtitles_guide_step_1: "Open a YouTube video and turn on its original captions.",
  dual_subtitles_guide_step_2: "Turn on Dual subtitles in Veksha. The translated line appears above the original one.",
  dual_subtitles_guide_step_3: "Use the globe button beside the captions to hide or show the translation without leaving the video.",
  dual_subtitles_guide_tip: "Hover over a word in the original captions to highlight the matching word in the translation.",
  grammar_memory_title: "Grammar Memory",
  grammar_memory_on: "Grammar Memory on",
  grammar_memory_off: "Grammar Memory",
  grammar_memory_scanning: "Analyzing visible text…",
  grammar_memory_disable: "Turn off Grammar Memory",
  grammar_memory_collapse: "Collapse the analysis",
  grammar_memory_expand: "Show grammar memory",
  grammar_hint_select: "Select a sentence on the page and press the 🔍 button next to it for a detailed grammar analysis.",
  grammar_analyze_selection: "Analyze the grammar of the selection",
  grammar_analysis_loading: "Analyzing the sentence…",
  grammar_analysis_failed: "Could not analyze the selection. Try again.",
  grammar_analysis_empty: "No notable grammar found in this selection.",
  grammar_roles_title: "Sentence roles",
  grammar_patterns_title: "Grammar in context",
  grammar_memory_patterns: "Your grammar memory",
  grammar_memory_loading: "Loading saved patterns…",
  grammar_memory_empty: "Patterns found while you read will collect here.",
  grammar_memory_seen: "Seen {n}×",
  grammar_memory_mastered: "Mark as mastered",
  grammar_memory_reopen: "Study again",
  grammar_memory_guide_title: "How Grammar Memory works",
  grammar_memory_guide_intro: "Grammar Memory turns patterns you encounter while reading into a personal, reusable collection.",
  grammar_memory_guide_step_1: "Turn on Grammar Memory while reading in your learning language. Veksha highlights sentence roles and detects useful constructions.",
  grammar_memory_guide_step_2: "Open the page panel to see saved patterns, explanations, real examples, and how often each pattern has appeared.",
  grammar_memory_guide_step_3: "Mark a pattern as mastered when it feels familiar. You can return it to learning at any time.",
  grammar_memory_guide_tip: "Select a sentence and use the grammar action to add a focused example to your memory.",
  grammar_role_subject: "Subject",
  grammar_role_verb: "Verb",
  grammar_role_object: "Object",
  grammar_role_place: "Place",
  grammar_role_time: "Time",
  grammar_role_modifier: "Modifier",
  my_words_title: "My words",
  my_words_intro: "A personal frequency list built from the words you actually encounter while browsing, tagged by site — not a generic top-1000 list.",
  my_words_on: "Tracking on",
  my_words_off: "Track my browsing",
  my_words_empty: "No words tracked yet. Turn tracking on and browse a few pages in your target language.",
  my_words_known: "Known",
  my_words_unknown: "Not yet known",
  my_words_seen_on: "{n}× · mostly on {domain}",
  my_words_add: "Add to dictionary",
  my_words_added: "Added to dictionary",
  my_words_add_error: "Could not add the word. Try again.",
  vocabulary_inbox_title: "From your translations",
  vocabulary_inbox_empty: "New vocabulary suggestions will appear here.",
  vocabulary_inbox_seen: "Seen {n}×",
  vocabulary_inbox_learn: "Learn",
  vocabulary_inbox_known: "I know it",
  vocabulary_inbox_ignore: "Ignore",
  vocabulary_inbox_error: "Could not update this suggestion. Try again.",
  my_words_guide_step_1: "Open your word list and turn tracking on there. Veksha counts words only on pages in your target language.",
  my_words_guide_step_2: "As you browse, a personal frequency list grows automatically and shows where each word appeared most often.",
  my_words_guide_step_3: "Add an unfamiliar word to your dictionary with one click, then practise it in training.",
  my_words_guide_tip: "The tile opens your word list, tracking is controlled inside it, and the question-mark button always opens this guide.",
  settings_title: "Settings",
  settings_intro: "Tell us your languages and level so we can pick the right words and difficulty for you.",
  settings_theme: "Theme",
  theme_light: "Light",
  theme_grove: "Colorful",
  theme_dark: "Dark",
  settings_display_name: "Your name",
  settings_native_lang: "Your language",
  settings_learning_languages: "Languages you study",
  settings_add_language: "Add a language",
  settings_remove_language: "Remove language",
  settings_target_lang: "Active learning language",
  settings_level: "My level",
  settings_level_placeholder: "Select your level...",
  settings_goals: "Your goals",
  settings_goals_placeholder: "e.g. Improve speaking, expand vocabulary, business English...",
  settings_prompt_label: "General prompt for AI",
  settings_prompt_placeholder: "e.g. Be supportive, correct my mistakes, explain grammar simply...",
  settings_mining_title: "Sentence Mining cards",
  settings_mining_desc: "Choose how many AI examples to generate when you open a saved word.",
  settings_mining_current: "At my current level",
  settings_mining_higher: "One level higher",
  settings_reminder_level: "Reminder intensity",
  settings_reminder_level_desc: "How insistently Veksha reminds you to train.",
  settings_reminder_level_1: "Just a notification",
  settings_reminder_level_2: "Noticeable card",
  settings_reminder_level_3: "Focus screen + frequent",
  settings_persistent: "Persistent reminders",
  settings_persistent_desc: "Hard-to-dismiss reminders: the close button runs away — finish a quick training or catch it to clear them.",
  settings_focus_guard: "Focus safeguard",
  settings_focus_guard_desc: "Turn reminders into a full-page decision: start now, snooze for 15 minutes, or intentionally pause for today.",
  settings_dual_subtitles: "Dual subtitles",
  settings_dual_subtitles_desc: "Enable translated subtitles and their playback control on YouTube.",
  settings_subscription: "Subscription",
  settings_sub_free: "Free plan",
  settings_sub_premium: "Premium — active until",
  settings_sub_premium_active: "Premium — active",
  settings_sub_desc: "Choose only the paid features you need and see the exact monthly total before payment.",
  settings_sub_connect: "Choose features",
  settings_sub_manage: "Change feature selection",
  settings_sub_err: "Could not open the payment form. Try again later.",
  settings_promo_label: "Promo code",
  settings_promo_placeholder: "Enter a promo code",
  settings_promo_submit: "Redeem",
  settings_promo_success: "Promo code redeemed — Premium unlocked.",
  settings_promo_error_invalid: "This promo code doesn't exist.",
  settings_promo_error_exhausted: "This promo code has already been fully claimed.",
  settings_promo_error_already_redeemed: "You've already redeemed this promo code.",
  settings_promo_error_generic: "Could not redeem the promo code. Try again later.",
  premium_required_title: "Feature not active",
  premium_required_desc: "{feature} isn't included in your subscription. Would you like to add it?",
  subscription_title: "Choose your features",
  subscription_intro_new: "All paid features are selected. Turn off anything you don't need — the total updates immediately.",
  subscription_intro_manage: "Your active features are selected. Adjust the set and continue to confirm the new subscription.",
  subscription_intro_add: "The requested feature and your current features are selected. Review the total before paying.",
  subscription_grammar_desc: "Collects grammar patterns and real examples from the texts you read.",
  subscription_monthly: "/ month",
  subscription_total: "Total",
  subscription_continue: "Continue to payment",
  subscription_opened: "The secure Telegram payment form has opened in a new tab.",
  subscription_empty: "Select at least one feature to continue.",
  subscription_load_error: "Could not load subscription options. Try again later.",
  subscription_cancel: "Cancel subscription",
  subscription_cancel_confirm: "Cancel the subscription and turn off all paid features now?",
  subscription_cancel_error: "Could not cancel the subscription. Try again later.",
  settings_account: "Account",
  settings_google_link: "Link Google account",
  settings_google_linked: "Google account linked",
  settings_google_link_taken: "This Google account is already linked to another profile.",
  settings_signout: "Sign out",
  settings_signout_confirm: "Sign out? Without a linked Google account you won't be able to get back into this profile.",
  settings_save: "Save",
  settings_saving: "Saving...",
  settings_translating: "Translating interface...",
  settings_err_no_level: "Please select your level.",
  settings_err_same_lang: "Native and target language must be different.",
  settings_err_load: "Could not load settings.",
  settings_err_save: "Could not save settings.",
  level_beginner: "Beginner (A1)",
  level_elementary: "Elementary (A2)",
  level_intermediate: "Intermediate (B1–B2)",
  level_upper_intermediate: "Upper-Intermediate (B2–C1)",
  level_advanced: "Advanced (C1–C2)",
  stats_title: "Statistics",
  stats_in_progress: "Words in progress",
  stats_known: "Words known",
  stats_topics: "Topics",
  stats_ready: "Ready to review now",
  stats_anki_reviews: "Card reviews",
  stats_training_reviews: "Training answers",
  stats_badge_new: "new",
  stats_badge_known: "known",
  stats_vocabulary: "Vocabulary",
  dictionary_title: "Dictionary",
  dictionary_cards: "Practice cards",
  dictionary_search_placeholder: "Search for a word…",
  dictionary_sort_label: "Sort words",
  dictionary_sort_az: "A–Z",
  dictionary_sort_za: "Z–A",
  dictionary_sort_newest: "Newest first",
  dictionary_sort_oldest: "Oldest first",
  dictionary_no_results: "No matching words found.",
  dictionary_translation: "Translation",
  dictionary_transcription: "Transcription",
  dictionary_show_answer: "Show answer",
  dictionary_again: "Again",
  dictionary_good: "Good",
  sentence_mining_title: "AI Sentence Mining card",
  sentence_mining_loading: "Creating examples, mnemonic and collocations…",
  sentence_mining_examples: "Examples",
  sentence_mining_mnemonic: "Mnemonic",
  sentence_mining_collocations: "Frequent collocations",
  sentence_mining_regenerate: "Regenerate",
  sentence_mining_error: "Could not create the AI card.",
  sentence_mining_level_up: "level up",
  stats_review_today: "review today",
  stats_review_in_days: "review in {n}d",
  stats_review_overdue: "review overdue",

  reminder_title: "Time to practice!",
  reminder_subtitle_default: "You have words to review.",
  reminder_words: "{n} word(s) to review",
  reminder_topic: "unfinished topic",
  reminder_have: "You have {items}.",
  reminder_start: "Start training",
  reminder_dismiss: "Dismiss reminder",
  reminder_focus_note: "Choose what happens next so this review does not disappear unnoticed.",
  reminder_snooze: "Remind me in 15 minutes",
  reminder_skip_today: "Pause for today",
  training_title: "Training",
  training_loading: "Loading task...",
  training_done: "Session complete — {n} words done!",
  training_empty: "No words to train yet. Translate and save words while you read — as soon as some are ready, training will unlock here automatically.",
  training_close: "Close",
  training_check: "Check",
  training_checking: "Checking...",
  training_next: "Next →",
  training_placeholder: "Your answer...",
  training_new_word: "New word",
  training_already_know: "I already know this",
  training_err_connect: "Could not connect to server.",
  training_err_lost: "Connection lost.",
  training_err_server: "Server error",
  practice_title: "Practice",
  practice_planning: "Choosing your next exercise...",
  practice_skill_recognition: "recognition",
  practice_skill_recall: "recall",
  practice_skill_contextual_meaning: "meaning in context",
  practice_skill_listening: "listening",
  practice_training_skill: "Training {skill}",
  practice_why_new_word: "A new word — let's start with {skill}.",
  practice_why_recent_error: "You missed this one last time, so {skill} again.",
  practice_why_weakest_skill: "You know this word, but {skill} is still behind.",
  practice_why_due_review: "Due for review, practising {skill}.",
  practice_why_skill_rotation: "Keeping {skill} fresh on this word.",
  practice_why_correction_support: "Working on the mistake — an easier {skill} task.",
  practice_why_correction_transfer: "Now the same {skill} on a new example.",
  practice_stage_support: "Working on the mistake",
  practice_stage_transfer: "Checking it stuck",
  practice_expected_answer: "Expected",
  practice_show_hint: "Show a hint",
  practice_replay: "Play again",
  practice_rating_label: "How well did you know it?",
  practice_rating_again: "Again",
  practice_rating_hard: "Hard",
  practice_rating_good: "Good",
  practice_rating_easy: "Easy",
  practice_rating_suggested: "Suggested: {rating}. Change it if you disagree.",
  practice_summary_corrections: "{n} mistake(s) worked on right away.",
  practice_summary_consolidated: "Consolidated",
  practice_summary_needs_work: "Still shaky",
  practice_summary_limited_by: "limited by {skill}",
  lesson_framing: "Working out what you need to be able to do…",
  lesson_loading_step: "Choosing your next step…",
  lesson_err_connect: "Could not connect to server.",
  lesson_err_lost: "Connection lost.",
  lesson_err_server: "Server error",
  lesson_err_no_goal: "Objective not specified.",
  lesson_resumed: "Picking up where you left off.",
  lesson_criteria_title: "To reach this objective",
  lesson_criteria_done: "{n} of {total} settled",
  lesson_time_left: "{n} min left",
  lesson_practice_hint: "Answer in your own words",
  lesson_finish_early: "Wrap up",
  lesson_next_step: "Next step",
  lesson_status_untested: "not checked yet",
  lesson_status_gap: "needs work",
  lesson_status_emerging: "coming along",
  lesson_status_implied: "shown by a harder answer",
  lesson_status_met: "demonstrated",
  lesson_activity_find_in_material: "Find it in your text",
  lesson_activity_explain_example: "Worked example",
  lesson_activity_compare_forms: "Tell them apart",
  lesson_activity_correct_error: "Fix the mistake",
  lesson_activity_predict_continuation: "Predict what follows",
  lesson_activity_paraphrase: "Say it another way",
  lesson_activity_create_example: "Build your own example",
  lesson_activity_role_reply: "Reply in role",
  lesson_activity_apply_unaided: "Final check — no hints",
  lesson_cause_unknown_term: "A word got in the way",
  lesson_cause_missed_signal: "The cue was there and went unnoticed",
  lesson_cause_rule_not_applied: "You know the rule — it just was not used here",
  lesson_cause_lucky_guess: "Right answer, but the reasoning is missing",
  lesson_cause_explains_not_produces: "You can explain it, not yet build it",
  lesson_cause_transfers_confidently: "Carried into a new situation",
  lesson_summary_achieved: "Objective reached",
  lesson_summary_out_of_time: "Time is up for this objective",
  lesson_summary_stopped: "Session ended",
  lesson_summary_proven: "What you can now do",
  lesson_summary_shaky: "Still unstable",
  lesson_summary_examples: "From your material",
  lesson_summary_next_goal: "Suggested next objective",
  lesson_summary_new_words: "New words saved as suggestions",
  lesson_summary_new_patterns: "New grammar patterns remembered",
  dictionary_empty: "Your dictionary has no saved entries yet.",
  quizlet_loading: "Loading Quizlet data…",
  quizlet_status_title: "Export status",
  quizlet_total_words: "Total words",
  quizlet_exported: "Exported",
  quizlet_not_exported: "Not exported",
  quizlet_export_options: "Export options",
  quizlet_exporting: "Exporting…",
  quizlet_export_new: "Export new ({n})",
  quizlet_export_all: "Export all ({n})",
  quizlet_export_new_hint: "Only words you have not exported yet.",
  quizlet_export_all_hint: "Every word in your vocabulary.",
  quizlet_format_hint: "Both options download a CSV file ready for Quizlet.",
  quizlet_import_title: "Import from Quizlet",
  quizlet_import_desc: "Upload a Quizlet CSV to add words to your vocabulary. Expected columns: Word, Translation, Context.",
  quizlet_importing: "Importing…",
  quizlet_select_csv: "Select CSV file",
  quizlet_imported: "Imported",
  quizlet_skipped: "Skipped",
  quizlet_errors: "Errors ({n})",
  quizlet_export_success: "Export complete. The file has been downloaded.",
  quizlet_export_steps_title: "How to export from Quizlet",
  quizlet_export_step_1: "Open your study set in Quizlet.",
  quizlet_export_step_2: "Open the three-dot menu (⋮).",
  quizlet_export_step_3: "Choose Export and select CSV.",
  quizlet_export_step_4: "Upload the downloaded file here.",
  quizlet_error_status: "Could not load Quizlet export status.",
  quizlet_error_export: "Could not export new words.",
  quizlet_error_export_all: "Could not export the vocabulary.",
  quizlet_error_csv: "Select a CSV file.",
  quizlet_error_import: "Could not import this file. Check its format and try again.",
  lesson_goals_kicker: "Learning objective",
  lesson_goals_prompt: "What should you be able to do?",
  lesson_goals_hint: "Describe a result you want to reach. The lesson turns it into checkable steps and adapts to your answers.",
  lesson_goals_placeholder: "For example: prepare for a project update call",
  lesson_goals_material_toggle: "Work from a text or situation",
  lesson_goals_material_placeholder: "Paste the article, message, or describe the situation",
  lesson_goals_minutes: "Minutes",
  lesson_goals_start: "Build lesson",
  lesson_goals_active: "Objectives in progress",
  lesson_goals_loading: "Loading your objectives…",
  lesson_goals_evidence: "{n} of {total} criteria settled",
  lesson_goals_continue: "Continue",
  lesson_goals_empty: "Your first objective will appear here after the lesson begins.",
  lesson_goals_load_failed: "Objectives could not be loaded. You can still start a new one.",
  lesson_goals_create_failed: "This objective could not be started. Try again.",
  common_back: "Back",
  home_translation_body: "Translate a word, phrase, or sentence and get a clean, in-context answer. Useful vocabulary goes to your inbox, so you decide what is worth learning.",
  home_quick_saved: "✓ saved for review",
  home_quick_suggested: "Review vocabulary suggestions →",
  home_hero_title: "Remember words,|without writing them out",
  nav_topics: "Topics",
  nav_training: "Training",
  nav_stats: "Statistics",
  nav_settings: "Settings",
  topbar_train: "Train",
  sub_topics: "Learn by topics — blocks with practice questions",
  sub_stats: "How much you've already remembered without writing",
  sub_settings: "Languages, level, reminders",
  sidebar_collected: "{n} words collected — no writing out",
  pdf_translate_region: "Translate area",
  pdf_region_hint: "Drag to select an area, then click the icon",
  pdf_no_text: "No text recognized in this area.",
  pdf_patch_dismiss: "Click to dismiss",
  ocr_capture_hint: "Drag across the text you want to translate.",
  ocr_recognized_text: "Recognized text",
  ocr_translate_selection: "Translate selection",
  ocr_choose_again: "Choose again",
  ocr_translate_area: "Translate area",
  ocr_copy_translation: "Copy translation",
  ocr_translation_copied: "Copied",
  content_translating: "Translating...",
  content_translate: "Translate selection",
  content_close: "Close",
  content_translation_failed: "Translation failed. Try again.",
  content_explanation_failed: "Explanation is unavailable.",
  content_explain: "More details",
  content_listen: "Listen",
  content_breakdown: "Break down",
  content_edit_text: "Edit text",
  content_hide_source: "Hide source",
  content_no_user: "Open the Veksha popup and enter your name first.",
  content_dualsubs: "Dual subtitles",
  level_setup_title: "Almost there!",
  level_setup_subtitle: "Tell us your level so we can pick the right tasks for you.",
  level_setup_optional: "optional",
  debug_title: "Debug",
  debug_user: "User",
  debug_backend: "Backend",
  debug_browser_lang: "Browser lang",
  debug_all_langs: "All langs",
  debug_commands: "Commands",
  debug_simulate_training_name: "Simulate completed training",
  debug_simulate_training_desc: "Advances 15 random words and one random topic as if training was completed.",
  debug_advance_day_name: "Move to tomorrow",
  debug_advance_day_desc: "Moves all word review dates one day back and triggers a reminder.",
  debug_reset_name: "Reset user data",
  debug_reset_desc: "Deletes all KB, session and settings on the server, then clears local storage. Registration starts from scratch.",
  debug_reset_confirm: "Reset ALL data for \"{username}\"? This cannot be undone.",
  debug_regen_name: "Regenerate translation",
  debug_regen_desc: "Re-translates the whole interface for your language from the current source strings. Use after UI text changes.",
  debug_regen_done: "Interface re-translated for {lang}.",
  debug_run: "Run",
  debug_reloading: "Reloading…",
};
