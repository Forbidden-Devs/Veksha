from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi import WebSocketDisconnect

from api import lesson_v2
from learning_core_v2.lesson import (
    LessonEvaluation,
    LessonMaterial,
    LessonQuestion,
    LessonSection,
    LessonTopic,
    LessonUnit,
    PreparedLesson,
)


def test_lesson_v2_preserves_public_paths():
    paths = {route.path for route in lesson_v2.router.routes}

    assert paths == {"/api/lesson-topics", "/api/lesson/ws"}


@dataclass
class FakeSettings:
    english_level: str = "b1"
    native_lang: str = "ru"
    target_lang: str = "en"
    goals: str = "travel"


@dataclass
class FakeStorage:
    settings: FakeSettings
    lessons: object | None = None
    saves: int = 0

    def save(self):
        self.saves += 1


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def receive_text(self):
        if not self.messages:
            raise WebSocketDisconnect()
        return json.dumps(self.messages.pop(0))

    async def send_json(self, value):
        self.sent.append(value)


class FakeRepository:
    def __init__(self, topic):
        self.topic = topic
        self.saved = []

    def find(self, _name):
        return self.topic

    def put(self, topic):
        self.topic = topic
        self.saved.append(topic)


class FakePreparer:
    def __init__(self, unit):
        self.unit = unit

    async def execute(self, topic, _profile):
        updated = LessonTopic(topic.name, units=(self.unit,))
        return PreparedLesson(updated, (self.unit,))


class FakeQuestionBuilder:
    async def execute(self, *, unit, **_values):
        return LessonQuestion("question-1", unit.name, "Explain the greeting")


class RecordingChecker:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return LessonEvaluation("correct", "Верно")


@pytest.mark.asyncio
async def test_websocket_uses_server_question_and_unit_when_checking(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "init", "topic_name": "Small talk"},
            {"type": "request_question"},
            {
                "type": "answer",
                "question_id": "question-1",
                "block_name": "tampered",
                "question": "tampered",
                "answer": "Hello!",
            },
        ]
    )
    material = LessonMaterial(
        "Greetings",
        "Start here.",
        (LessonSection("Pattern", items=("Hello!",)),),
    )
    unit = LessonUnit("Greetings", material)
    repository = FakeRepository(LessonTopic("Small talk"))
    checker = RecordingChecker()

    async def authenticated(_socket):
        return "tester"

    monkeypatch.setattr(lesson_v2, "ws_current_user", authenticated)
    monkeypatch.setattr(
        lesson_v2,
        "get_storage",
        lambda _username: FakeStorage(FakeSettings(), repository),
    )
    monkeypatch.setattr(
        lesson_v2,
        "build_lesson_services",
        lambda: (FakePreparer(unit), FakeQuestionBuilder(), checker),
    )

    await lesson_v2.lesson_ws(socket)

    assert checker.requests[0].unit.name == "Greetings"
    assert checker.requests[0].question == "Explain the greeting"
    assert repository.saved[-1].units[0].history[0].question == "Explain the greeting"
    assert [message["type"] for message in socket.sent] == [
        "ready",
        "question",
        "result",
    ]
