from __future__ import annotations

import pytest

from learning_core_v2.lesson import (
    AnswerRequest,
    BuildLessonQuestion,
    CheckLessonAnswer,
    LearnerProfile,
    LessonEvaluation,
    LessonMaterial,
    LessonSection,
    LessonTopic,
    LessonUnit,
    PrepareLesson,
    QuestionSchedule,
    RecordedAnswer,
    RecordLessonResults,
    TopicReviewPolicy,
    create_topic,
    summarize_topic,
)


PROFILE = LearnerProfile("B1", "ru", "en", "work conversations")


class StubAuthor:
    def __init__(self) -> None:
        self.proposed = ["Foundations", "Everyday use"]
        self.questions: list[str] = []

    async def propose_units(self, request):
        return self.proposed[: request.requested_count]

    async def write_material(self, request):
        return LessonMaterial(
            title=f" {request.unit} ",
            intro=" Short introduction ",
            sections=(
                LessonSection(
                    header=" Key idea ", items=(" First point ", ""), highlight=True
                ),
            ),
        )

    async def write_question(self, request):
        self.questions.extend(request.previous_questions)
        return f"Explain {request.unit.name}"

    async def evaluate_lesson_answer(self, request):
        return LessonEvaluation("correct", " Good answer ")


class IDs:
    def new(self):
        return "question-1"


@pytest.mark.asyncio
async def test_preparation_authors_missing_units_and_normalizes_material():
    author = StubAuthor()
    prepared = await PrepareLesson(author).execute(create_topic("  Travel   English "), PROFILE)

    assert prepared.topic.name == "Travel English"
    assert [unit.name for unit in prepared.units] == ["Foundations", "Everyday use"]
    assert prepared.units[0].material == LessonMaterial(
        title="Foundations",
        intro="Short introduction",
        sections=(
            LessonSection(
                header="Key idea", items=("First point",), highlight=True
            ),
        ),
    )


@pytest.mark.asyncio
async def test_preparation_prefers_low_mastery_existing_material():
    author = StubAuthor()
    material = LessonMaterial(
        "Title", "Intro", (LessonSection("Rule", text="Explanation"),)
    )
    topic = LessonTopic(
        "Travel",
        units=(
            LessonUnit("Mastered", material, mastery=0.9),
            LessonUnit("Needs practice", material, mastery=0.2),
            LessonUnit("Developing", material, mastery=0.5),
        ),
    )

    prepared = await PrepareLesson(author).execute(topic, PROFILE)

    assert [unit.name for unit in prepared.units] == ["Needs practice", "Developing"]


@pytest.mark.asyncio
async def test_preparation_finishes_pending_units_before_extending_curriculum():
    author = StubAuthor()
    topic = LessonTopic(
        "Travel", units=(LessonUnit("Existing outline"),), curriculum_exhausted=True
    )

    prepared = await PrepareLesson(author).execute(topic, PROFILE)

    assert [unit.name for unit in prepared.units] == ["Existing outline"]
    assert prepared.units[0].material is not None


def test_schedule_balances_questions_across_available_units():
    material = LessonMaterial(
        "Title", "Intro", (LessonSection("Rule", text="Explanation"),)
    )
    units = [LessonUnit("A", material), LessonUnit("B", material)]

    assert QuestionSchedule(5).arrange(units) == ("A", "B", "A", "B", "A")


@pytest.mark.asyncio
async def test_questions_get_server_identifiers_and_empty_answers_skip_author():
    author = StubAuthor()
    material = LessonMaterial(
        "Title", "Intro", (LessonSection("Rule", text="Explanation"),)
    )
    unit = LessonUnit("Basics", material)
    question = await BuildLessonQuestion(author, IDs()).execute(
        topic="Travel",
        unit=unit,
        previous_questions=["Earlier question"],
        profile=PROFILE,
    )

    assert question.question_id == "question-1"
    assert question.text == "Explain Basics"
    assert author.questions == ["Earlier question"]

    result = await CheckLessonAnswer(author).execute(
        AnswerRequest("Travel", unit, question.text, "   ", PROFILE)
    )
    assert result.outcome == "garbage"
    assert not result.should_record


def test_results_accumulate_evidence_and_ignore_garbage():
    unit = LessonUnit("Basics", mastery=0.5)
    topic = LessonTopic("Travel", units=(unit,))

    updated = RecordLessonResults().execute(
        topic,
        {
            "Basics": [
                RecordedAnswer("Q1", "correct"),
                RecordedAnswer("Q2", "incorrect"),
                RecordedAnswer("Q3", "garbage"),
            ]
        },
        reviewed_at=42.0,
    )

    assert updated.units[0].mastery == pytest.approx(0.5)
    assert [item.question for item in updated.units[0].history] == ["Q1", "Q2"]
    assert updated.last_reviewed_at == 42.0


def test_summary_counts_only_authored_units():
    material = LessonMaterial(
        "Title", "Intro", (LessonSection("Rule", text="Explanation"),)
    )
    topic = LessonTopic(
        "Travel",
        units=(LessonUnit("Ready", material, 0.8), LessonUnit("Draft")),
        last_reviewed_at=10.0,
    )

    assert summarize_topic(topic).unit_count == 1
    assert summarize_topic(topic).mastery == 0.8


def test_review_policy_ignores_empty_topics_and_returns_first_due_topic():
    material = LessonMaterial(
        "Title", "Intro", (LessonSection("Rule", text="Explanation"),)
    )
    topics = [
        LessonTopic("Empty"),
        LessonTopic("Mastered", units=(LessonUnit("A", material, 0.9),)),
        LessonTopic("Due", units=(LessonUnit("B", material, 0.4),)),
    ]

    assert TopicReviewPolicy().first_due(topics) == "Due"


@pytest.mark.asyncio
async def test_invalid_topic_and_incomplete_material_are_rejected():
    with pytest.raises(ValueError):
        create_topic("   ")

    class IncompleteAuthor(StubAuthor):
        async def write_material(self, request):
            return LessonMaterial("", "", ())

    with pytest.raises(ValueError, match="incomplete material"):
        await PrepareLesson(IncompleteAuthor()).execute(create_topic("Travel"), PROFILE)
