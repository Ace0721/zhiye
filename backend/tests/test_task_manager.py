import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db import Base, create_database
from app.models import Card, Task
from app.services.ai_client import AIError
from app.services.parser import TextBlock
from app.services.task_manager import TaskManager
from conftest import card_json


class MockClient:
    closed = False

    def __init__(self, *_args) -> None:
        pass

    async def complete(self, prompt: str, text: str) -> str:
        if text == "bad":
            raise AIError("认证失败")
        if text == "empty":
            return "[]"
        if text == "slow":
            await asyncio.sleep(10)
        return card_json()

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def manager(config: Settings):
    engine, sessions = create_database(config)
    Base.metadata.create_all(engine)
    manager = TaskManager(config, sessions, client_factory=MockClient)
    manager.generator.retry_delay = 0
    yield manager
    engine.dispose()


async def run_task(manager: TaskManager, texts: list[str]):
    manager.parser = lambda *_args: [TextBlock(index, f"第 {index + 1} 页", text) for index, text in enumerate(texts)]
    path = manager.upload_dir / "upload-test.pdf"
    path.write_bytes(b"mock")
    task_id = manager.submit(path, "lecture.pdf")
    await asyncio.wait_for(manager.running[task_id], timeout=2)
    assert not path.exists()
    return task_id, manager.snapshot(task_id)


async def test_partial_success_persisted_and_restart_keeps_cards(manager: TaskManager) -> None:
    task_id, state = await run_task(manager, ["good", "bad", "good"])
    assert state.status == "completed"
    assert state.progress == 100 and state.done_blocks == 3
    assert state.card_count == 2 and len(state.failed_blocks) == 1
    with manager.sessions() as session:
        cards = session.scalars(select(Card).order_by(Card.order_index)).all()
        assert [card.order_index for card in cards] == [0, 1]
    manager.recover()
    assert manager.snapshot(task_id).model_dump() == state.model_dump()


@pytest.mark.parametrize("texts, expected", [(["bad", "bad"], "认证失败"), (["empty"], "没有可生成的学科知识点")])
async def test_all_failed_or_no_cards(manager: TaskManager, texts: list[str], expected: str) -> None:
    _, state = await run_task(manager, texts)
    assert state.status == "failed"
    assert state.deck_id is None and state.card_count == 0
    assert expected in state.error


async def test_timeout_marks_failed_and_stops_calls(manager: TaskManager) -> None:
    manager.config.task_timeout = 0.03
    _, state = await run_task(manager, ["slow", "slow", "slow"])
    assert state.status == "failed"
    assert "超时" in state.error


def test_startup_recovers_unfinished_tasks(manager: TaskManager) -> None:
    with manager.sessions.begin() as session:
        session.add_all([Task(id=status, status=status) for status in ["queued", "parsing", "generating"]])
    orphan = manager.upload_dir / "upload-orphan.pdf"
    orphan.write_bytes(b"orphan")
    manager.recover()
    for status in ["queued", "parsing", "generating"]:
        state = manager.snapshot(status)
        assert state.status == "failed" and "重启" in state.error
    assert not orphan.exists()


async def test_shutdown_cancels_running_task(manager: TaskManager) -> None:
    manager.parser = lambda *_args: [TextBlock(0, "page", "slow")]
    path = manager.upload_dir / "upload-shutdown.pdf"
    path.write_bytes(b"mock")
    task_id = manager.submit(path, "lecture.pdf")
    await asyncio.sleep(0.02)
    await manager.shutdown()
    assert manager.snapshot(task_id).status == "failed"
    assert not path.exists()
