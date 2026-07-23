"""
llm — all OpenAI API calls for Veksha.

Organized by domain:
  llm.metadata   — extract_metadata
  llm.training   — check_synonym_appropriate, get_reverse_translations,
                    check_training_answer
  llm.lesson     — suggest_block_names, generate_block_content,
                    review_block_content, generate_lesson_question, check_lesson_answer
  llm.selection  — translate_selection, explain_selection
  llm.immersion  — analyze_block
  llm.ci_meter   — classify_difficulty
  llm.grammar_lens — analyze_grammar_block
  llm._base      — _call, helpers (private)
"""
from llm.metadata import extract_metadata
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
from llm.grammar_lens import analyze_grammar_block
from llm.sentence_mining import generate_sentence_mining

__all__ = [
    "extract_metadata",
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
    "analyze_grammar_block",
    "generate_sentence_mining",
]
