"""
llm — all OpenAI API calls for Veksha.

Organized by domain:
  llm.pipeline   — input_processor, extract_metadata, update_knowledge_base,
                    match_delete_candidate, unknown_message
  llm.training   — check_synonym_appropriate, get_reverse_translations,
                    check_training_answer
  llm.lesson     — suggest_block_names, generate_block_content,
                    review_block_content, generate_lesson_question, check_lesson_answer
  llm.selection  — translate_selection, explain_selection
  llm.immersion  — analyze_block
  llm.ci_meter   — classify_difficulty
  llm._base      — _call, helpers (private)
"""
from llm.pipeline import (
    input_processor,
    extract_metadata,
    update_knowledge_base,
    match_delete_candidate,
    unknown_message,
)
from llm.training import (
    check_synonym_appropriate,
    get_reverse_translations,
    check_training_answer,
)
from llm.lesson import (
    suggest_block_names,
    generate_block_content,
    review_block_content,
    generate_lesson_question,
    check_lesson_answer,
)
from llm.selection import (
    translate_selection,
    explain_selection,
)
from llm.immersion import analyze_block
from llm.ci_meter import classify_difficulty

__all__ = [
    "input_processor",
    "extract_metadata",
    "update_knowledge_base",
    "match_delete_candidate",
    "unknown_message",
    "check_synonym_appropriate",
    "get_reverse_translations",
    "check_training_answer",
    "suggest_block_names",
    "generate_block_content",
    "review_block_content",
    "generate_lesson_question",
    "check_lesson_answer",
    "translate_selection",
    "explain_selection",
    "analyze_block",
    "classify_difficulty",
]
