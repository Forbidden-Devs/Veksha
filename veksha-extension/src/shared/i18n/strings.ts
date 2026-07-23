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
  // Chat
  chat_reminders: string;
  chat_today: string;
  chat_placeholder: string;
  chat_mode_training: string;
  chat_mode_lesson: string;
  chat_mode_assistant: string;
  chat_mode_translate: string;
  chat_explain: string;
  chat_listen: string;
  immersion_on: string;
  immersion_off: string;
  immersion_hint: string;
  ci_meter_on: string;
  ci_meter_off: string;
  ci_meter_loading: string;
  ci_meter_refine: string;
  ci_meter_badge_known: string;
  ci_meter_verdict_ideal: string;
  ci_meter_verdict_too_easy: string;
  ci_meter_verdict_too_hard: string;
  ci_meter_verdict_close: string;
  grammar_lens_title: string;
  grammar_lens_on: string;
  grammar_lens_off: string;
  grammar_lens_loading: string;
  grammar_lens_disable: string;
  grammar_patterns_title: string;
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
  // Settings
  settings_title: string;
  settings_intro: string;
  settings_theme: string;
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
  // Training window
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
  // Lesson window
  lesson_preparing: string;
  lesson_loading_question: string;
  lesson_done: string;        // placeholder: {n}
  lesson_err_connect: string;
  lesson_err_lost: string;
  lesson_err_server: string;
  lesson_err_no_topic: string;
  lesson_block_of: string;    // placeholders: {n}, {total}
  lesson_scroll_next: string;
  lesson_practice: string;
  lesson_practice_hint: string;
  // Topic picker
  topics_loading: string;
  topics_empty: string;
  topics_empty_title: string;
  topics_empty_hint: string;
  topics_blocks: string;      // placeholder: {n}
  topics_placeholder: string;
  topics_add: string;
  // First-run tutorial
  tutorial_skip: string;
  tutorial_back: string;
  tutorial_next: string;
  tutorial_start: string;
  tutorial_s1_title: string;
  tutorial_s1_body: string;
  tutorial_s2_title: string;
  tutorial_s2_body: string;
  tutorial_s3_title: string;
  tutorial_s3_body: string;
  tutorial_s4_title: string;
  tutorial_s4_body: string;
  tutorial_train_title: string;
  tutorial_train_body: string;
  tutorial_imm_title: string;
  tutorial_imm_lead: string;
  tutorial_imm_heading: string;
  tutorial_imm_p1_term: string;
  tutorial_imm_p1_desc: string;
  tutorial_imm_p2_term: string;
  tutorial_imm_p2_desc: string;
  tutorial_imm_p3_term: string;
  tutorial_imm_p3_desc: string;
  tutorial_imm_p4_term: string;
  tutorial_imm_p4_desc: string;
  tutorial_s7_title: string;
  tutorial_s7_body: string;
  tutorial_s8_title: string;
  tutorial_s8_body: string;
  help_title: string;
  help_body: string;
  help_start: string;
  // Post-registration tour (8 animated scenes). Titles use "|" to split the
  // gradient-accented second line.
  tour_skip: string;
  tour_back: string;
  tour_next: string;
  tour_next_first: string;
  tour_start: string;
  tour_replay: string;
  tour_kb: string;
  tour_saved: string;
  tour_region_tag: string;
  tour_tt_title: string;
  tour_tt_sub: string;
  tour_q_badge: string;
  tour_q_ctx: string;
  tour_q_fb: string;
  tour_s0_step: string;
  tour_s0_title: string;
  tour_s0_text: string;
  tour_s1_step: string;
  tour_s1_title: string;
  tour_s1_text: string;
  tour_s1_tag: string;
  tour_s2_step: string;
  tour_s2_title: string;
  tour_s2_text: string;
  tour_s2_tag: string;
  tour_s3_step: string;
  tour_s3_title: string;
  tour_s3_text: string;
  tour_s3_tag: string;
  tour_s4_step: string;
  tour_s4_title: string;
  tour_s4_text: string;
  tour_s4_tag: string;
  tour_s5_step: string;
  tour_s5_title: string;
  tour_s5_text: string;
  tour_s5_tag: string;
  tour_s6_step: string;
  tour_s6_title: string;
  tour_s6_text: string;
  tour_s6_tag: string;
  tour_s7_step: string;
  tour_s7_title: string;
  tour_s7_text: string;
  // Assistant default greeting + suggestion chips
  chat_greeting: string;
  chat_chip_topic: string;
  chat_chip_words: string;
  chat_chip_explain: string;
  // Immersion explainer modal (shown on enable until "I already know")
  imm_modal_title: string;
  imm_modal_sub: string;
  imm_card1_title: string;
  imm_card1_desc: string;
  imm_card2_title: string;
  imm_card2_desc: string;
  imm_card3_title: string;
  imm_card3_desc: string;
  imm_modal_known: string;
  imm_modal_ok: string;
  // App shell (sidebar + topbar)
  nav_assistant: string;
  nav_topics: string;
  nav_training: string;
  nav_immersion: string;
  nav_stats: string;
  nav_settings: string;
  topbar_train: string;
  sub_assistant: string;
  sub_topics: string;
  sub_stats: string;
  sub_settings: string;
  sidebar_collected: string;  // placeholder: {n}
  home_ask_placeholder: string;
  // PDF area translate (OCR)
  pdf_translate_region: string;
  pdf_region_hint: string;
  pdf_no_text: string;
  pdf_patch_dismiss: string;
  // Content script (translation popup on page)
  content_translating: string;
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
  chat_reminders: "Reminders",
  chat_today: "Today",
  chat_placeholder: "Write a message...",
  chat_mode_training: "Training",
  chat_mode_lesson: "Lesson",
  chat_mode_assistant: "Assistant",
  chat_mode_translate: "Translate",
  chat_explain: "More details",
  chat_listen: "Listen",
  immersion_on: "Immersion on",
  immersion_off: "Immerse page",
  immersion_hint: "Sprinkle level-appropriate sentences in your target language right into the pages you read.",
  ci_meter_on: "CI meter on",
  ci_meter_off: "CI meter",
  ci_meter_loading: "Checking readability…",
  ci_meter_refine: "Refine with AI",
  ci_meter_badge_known: "{pct}% known · {cefr}",
  ci_meter_verdict_ideal: "Great i+1 content for you — mostly familiar with a healthy stretch of new words.",
  ci_meter_verdict_too_easy: "You know this well already — good for fluency practice, but little new vocabulary.",
  ci_meter_verdict_too_hard: "This may be too difficult right now — expect to look up a lot of words.",
  ci_meter_verdict_close: "Close to your level.",
  grammar_lens_title: "Grammar Lens",
  grammar_lens_on: "Grammar Lens on",
  grammar_lens_off: "Grammar Lens",
  grammar_lens_loading: "Analyzing visible text…",
  grammar_lens_disable: "Turn off Grammar Lens",
  grammar_patterns_title: "Grammar in context",
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
  settings_title: "Settings",
  settings_intro: "Tell us your languages and level so we can pick the right words and difficulty for you.",
  settings_theme: "Theme",
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
  settings_reminder_level_2: "Pop-up with blur",
  settings_reminder_level_3: "Blur + frequent",
  settings_persistent: "Persistent reminders",
  settings_persistent_desc: "Hard-to-dismiss reminders: the close button runs away — finish a quick training or catch it to clear them.",
  settings_dual_subtitles: "Dual subtitles",
  settings_dual_subtitles_desc: "Enable translated subtitles and their playback control on YouTube.",
  settings_subscription: "Subscription",
  settings_sub_free: "Free plan",
  settings_sub_premium: "Premium — active until",
  settings_sub_premium_active: "Premium — active",
  settings_sub_desc: "Premium unlocks Grammar Lens, page immersion and dual subtitles.",
  settings_sub_connect: "Subscribe via Telegram",
  settings_sub_manage: "Manage in Telegram",
  settings_sub_err: "Could not open the subscription bot. Try again later.",
  settings_promo_label: "Promo code",
  settings_promo_placeholder: "Enter a promo code",
  settings_promo_submit: "Redeem",
  settings_promo_success: "Promo code redeemed — Premium unlocked.",
  settings_promo_error_invalid: "This promo code doesn't exist.",
  settings_promo_error_exhausted: "This promo code has already been fully claimed.",
  settings_promo_error_already_redeemed: "You've already redeemed this promo code.",
  settings_promo_error_generic: "Could not redeem the promo code. Try again later.",
  premium_required_title: "Premium required",
  premium_required_desc: "{feature} requires an active Premium subscription.",
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
  lesson_preparing: "Preparing material...",
  lesson_loading_question: "Loading question...",
  lesson_done: "Session complete — {n} question(s) done!",
  lesson_err_connect: "Could not connect to server.",
  lesson_err_lost: "Connection lost.",
  lesson_err_server: "Server error",
  lesson_err_no_topic: "Topic not specified.",
  lesson_block_of: "Block {n} of {total}",
  lesson_scroll_next: "Keep scrolling for the next block",
  lesson_practice: "Practice",
  lesson_practice_hint: "Answer in your own words",
  topics_loading: "Loading topics...",
  topics_empty: "No topics yet. Add your first topic below.",
  topics_empty_title: "What would you like to master?",
  topics_empty_hint: 'Type the name of a topic you\'d like to understand in English — for example “Tenses”, “Medical terminology”, or anything else.',
  topics_blocks: "{n} block(s)",
  topics_placeholder: "e.g. Tenses, Medical terminology…",
  topics_add: "Add",
  tutorial_skip: "Skip",
  tutorial_back: "Back",
  tutorial_next: "Next",
  tutorial_start: "Start reading",
  tutorial_s1_title: "Just translate. Veksha does the learning.",
  tutorial_s1_body: "You read. You translate words you don't know. That's it. Behind the scenes Veksha remembers every word you look up, analyzes what you translate, and teaches it back to you at the right moment. Let's show you how.",
  tutorial_s2_title: "Translate anything, anywhere",
  tutorial_s2_body: "Select any word while you read and get its meaning instantly — right in context. There's even a special mode for YouTube subtitles, so you can learn straight from videos. This is the only step you do — and every word you look up is quietly saved to learn later.",
  tutorial_s3_title: "An assistant that does the work for you",
  tutorial_s3_body: "Veksha analyzes what you translate and look up — the words and patterns that actually matter for you. The assistant chat turns that into action: it suggests words worth learning, adds them to your vocabulary, and builds study topics. You don't put anything together; just ask, and it's done.",
  tutorial_s4_title: "A chat made only for translation",
  tutorial_s4_body: "When you want to translate freely, the dedicated translation chat is always there. Type a word, phrase, or sentence — get a clean, in-context answer. And every translation is remembered and analyzed, quietly becoming something to review later.",
  tutorial_train_title: "Your words come back when it counts",
  tutorial_train_body: "Every word you translate is saved and tracked for you. Training brings each one back with spaced repetition — right before you'd forget it — so it actually sticks. No flashcards to make: Veksha already knows which words you need and exactly when.",
  tutorial_imm_title: "One tap into immersion",
  tutorial_imm_lead: "Veksha replaces part of the sentences and words you read with their version in the language you're learning. Only a portion of the text is swapped — right where it sits — so the page stays easy to read while new language slips in naturally.",
  tutorial_imm_heading: "What immersion actually does",
  tutorial_imm_p1_term: "Only part of the text",
  tutorial_imm_p1_desc: "Veksha swaps in just some phrases — not the whole page — so reading stays natural while new language slips in.",
  tutorial_imm_p2_term: "Comprehensible input",
  tutorial_imm_p2_desc: "You already understand the rest, so each translated bit clicks from context instead of rote memorization.",
  tutorial_imm_p3_term: "Tuned to your level (i + 1)",
  tutorial_imm_p3_desc: "What gets translated sits just one step above what you know — the sweet spot where a language truly sticks.",
  tutorial_imm_p4_term: "Adaptive, in the background",
  tutorial_imm_p4_desc: "It leans on the words you've saved and how well you know them, growing bolder as you improve — while you just keep reading.",
  tutorial_s7_title: "You translate. Veksha teaches.",
  tutorial_s7_body: "That's the whole idea. Everything you look up is remembered, analyzed, and brought back at the right moment. Start reading — Veksha handles the rest.",
  tutorial_s8_title: "Go deep on any topic",
  tutorial_s8_body: "Open the menu to add a topic — “Tenses”, “Medical terminology”, anything — or pick one that's ready. Veksha builds a structured lesson from it: clear blocks you move through at your own pace, with hands-on practice questions checked in real time.",
  help_title: "Need a hand?",
  help_body: "Take a quick tour of Veksha",
  help_start: "Start tour",
  tour_skip: "Skip",
  tour_back: "Back",
  tour_next: "Next",
  tour_next_first: "Show me how it works",
  tour_start: "Start →",
  tour_replay: "↻ replay animation",
  tour_kb: "Knowledge base",
  tour_saved: "✓ saved for review",
  tour_region_tag: "Select an area to translate",
  tour_tt_title: "Time to review!",
  tour_tt_sub: "5 words are ready for training",
  tour_q_badge: "Reverse translation",
  tour_q_ctx: "You saw it in the video: majestic fjords — now say it in the language you're learning.",
  tour_q_fb: "✓ Correct! The word moves into long-term memory.",
  tour_s0_step: "Welcome",
  tour_s0_title: "Remember words,|without writing them out",
  tour_s0_text: "You simply use a handy translator — Veksha makes sure you remember everything.",
  tour_s1_step: "Step 1 · Text",
  tour_s1_title: "Select text —|it's already yours",
  tour_s1_text: "Select it like ordinary text — the contextual translator appears instantly. And the word quietly flies into your knowledge base for review.",
  tour_s1_tag: "🚀 Flies to the base automatically",
  tour_s2_step: "Step 2 · Smart pick",
  tour_s2_title: "Select a paragraph —|we keep only the hard part",
  tour_s2_text: "From a big text Veksha pulls out the words that match your level. Easy ones are skipped, hard ones are saved.",
  tour_s2_tag: "🎯 Words at your level",
  tour_s3_step: "Step 3 · YouTube",
  tour_s3_title: "Watch a video —|translate the subtitles",
  tour_s3_text: "Tap a word right in the subtitles. It gets translated and lands in your base — same as when reading.",
  tour_s3_tag: "▶ Works in subtitles",
  tour_s4_step: "Step 4 · Documents",
  tour_s4_title: "Even in PDF —|via the menu",
  tour_s4_text: "Select text, right-click → “Translate in Veksha”. Works even in documents and books.",
  tour_s4_tag: "📄 An item in the context menu",
  tour_s5_step: "Step 5 · Images",
  tour_s5_title: "Text on a picture?|Select the area",
  tour_s5_text: "Draw a box right over the image — Veksha reads the text and translates it. Posters, memes, screenshots.",
  tour_s5_tag: "🖼️ Area selection over a photo",
  tour_s6_step: "Step 6 · Review",
  tour_s6_title: "And then —|it reminds you itself",
  tour_s6_text: "At the right moment Veksha calls you to a short training and asks exactly what you translated.",
  tour_s6_tag: "🔁 Brings words back at the right moment",
  tour_s7_step: "Done",
  tour_s7_title: "Use me|as your translator",
  tour_s7_text: "That's all you do. Everything else — remembering, reminding, training — I handle myself.",
  chat_greeting: "Hi 👋 I can put together a study topic or toss in words for training. What shall we do?",
  chat_chip_topic: "Build a marketing topic",
  chat_chip_words: "Give me 6 words about coffee",
  chat_chip_explain: "Explain the difference in/on/at",
  imm_modal_title: "Immersion mode is on",
  imm_modal_sub: "Some words on the pages you read are replaced with the language you're learning — right as you read.",
  imm_card1_title: "Only part of the text",
  imm_card1_desc: "Not the whole page — just a few phrases. Reading stays easy.",
  imm_card2_title: "Clear from context",
  imm_card2_desc: "The meaning is obvious from the surrounding words — no dictionary, no cramming.",
  imm_card3_title: "Matched to your level",
  imm_card3_desc: "One step above what you already know — that's where language sticks.",
  imm_modal_known: "I already know",
  imm_modal_ok: "Got it",
  nav_assistant: "Assistant",
  nav_topics: "Topics",
  nav_training: "Training",
  nav_immersion: "Immersion",
  nav_stats: "Statistics",
  nav_settings: "Settings",
  topbar_train: "Train",
  sub_assistant: "Ask anything, translate, or generate words to learn",
  sub_topics: "Learn by topics — blocks with practice questions",
  sub_stats: "How much you've already remembered without writing",
  sub_settings: "Languages, level, reminders",
  sidebar_collected: "{n} words collected — no writing out",
  home_ask_placeholder: "Ask or type anything…",
  pdf_translate_region: "Translate area",
  pdf_region_hint: "Drag to select an area, then click the icon",
  pdf_no_text: "No text recognized in this area.",
  pdf_patch_dismiss: "Click to dismiss",
  content_translating: "Translating...",
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
