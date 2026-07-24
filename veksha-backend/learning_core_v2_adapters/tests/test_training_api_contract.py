import json
from dataclasses import dataclass

import pytest
from fastapi import WebSocketDisconnect

from api import training_v2
from learning_core_v2.practice import AnswerEvaluation, PracticeTask, PracticeWord


def test_training_v2_preserves_public_paths():
    paths = {route.path for route in training_v2.router.routes}

    assert paths == {
        "/api/training/init",
        "/api/training/validate",
        "/api/training/review_log",
        "/api/training/ws",
    }


@dataclass
class FakeSettings:
    english_level: str = "b1"
    native_lang: str = "ru"
    target_lang: str = "en"


@dataclass
class FakeStorage:
    settings: FakeSettings


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
    def __init__(self):
        self.applied = []

    def words(self):
        return [PracticeWord("run", "en", translation="бежать")]

    def apply_evaluation(self, word, evaluation, kind):
        self.applied.append((word, evaluation.outcome, kind))
        return True

    def mark_known(self, _word):
        return False


class FakeBuilder:
    async def execute(self, word, **_settings):
        return PracticeTask(
            "task-1",
            word.text,
            word.context,
            "translation",
            "Переведите слово run",
            word.review_count,
            "Recall",
        )


class RecordingChecker:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return AnswerEvaluation("correct", "Верно")


@pytest.mark.asyncio
async def test_websocket_ignores_client_word_and_question_when_checking(monkeypatch):
    socket = FakeWebSocket(
        [
            {"type": "request_task"},
            {
                "type": "answer",
                "task_id": "task-1",
                "word": "tampered",
                "question": "tampered",
                "answer": "бежать",
            },
        ]
    )
    repository = FakeRepository()
    checker = RecordingChecker()

    async def authenticated(_socket):
        return "tester"

    monkeypatch.setattr(training_v2, "ws_current_user", authenticated)
    monkeypatch.setattr(
        training_v2, "get_storage", lambda _username: FakeStorage(FakeSettings())
    )
    monkeypatch.setattr(
        training_v2, "UserStoragePracticeRepository", lambda _storage: repository
    )
    monkeypatch.setattr(
        training_v2,
        "build_practice_services",
        lambda: (FakeBuilder(), checker),
    )

    await training_v2.training_ws(socket)

    assert checker.requests[0].task.word == "run"
    assert checker.requests[0].task.question == "Переведите слово run"
    assert repository.applied == [("run", "correct", "translation")]
    assert [message["type"] for message in socket.sent] == ["task", "result"]
