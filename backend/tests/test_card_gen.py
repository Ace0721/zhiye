import asyncio
import json
from collections import Counter

import pytest

from app.schemas import FailedBlock
from app.services.ai_client import AIError
from app.services.card_gen import CardGenerator, is_course_admin_card, parse_cards
from app.services.parser import TextBlock
from conftest import card_json


async def ignore_progress(done: int, failures: list[FailedBlock]) -> None:
    pass


@pytest.mark.parametrize("title, question, excluded", [
    ("课程总课时与章节", "关于本课程的学时与章节安排，正确的是？", True),
    ("学时分配", "第七章安排多少学时？", True),
    ("成绩构成", "期末成绩的占比是多少？", True),
    ("任课教师联系方式", "如何联系任课教师？", True),
    ("CPU执行时间", "时钟周期如何影响CPU执行时间？", False),
    ("诉讼程序", "诉讼程序包含哪些阶段？", False),
    ("学分制的定义", "学分制与学年制有什么区别？", False),
])
def test_course_admin_filter_preserves_subject_knowledge(title: str, question: str, excluded: bool) -> None:
    data = json.loads(card_json(title))
    data[0]["question"] = question
    assert is_course_admin_card(parse_cards(json.dumps(data))[0]) is excluded


async def test_mixed_block_filters_admin_but_keeps_knowledge_in_order() -> None:
    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            assert "本块没有值得学习的学科知识时返回 []" in prompt
            cards = json.loads(card_json("课程学时安排"))
            cards += json.loads(card_json("诉讼程序")) + json.loads(card_json("举证责任"))
            return json.dumps(cards)

    result = await CardGenerator(asyncio.Semaphore(1), 1, 0).generate(blocks(1), Client(), ignore_progress)
    assert [card.title for card in result.cards] == ["诉讼程序", "举证责任"]
    assert result.success_blocks == 1
    assert not result.failed_blocks


async def test_admin_only_blocks_are_skipped_without_retry_or_failure() -> None:
    calls = 0

    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            nonlocal calls
            calls += 1
            return "[]" if text == "0" else card_json("课程学时安排")

    result = await CardGenerator(asyncio.Semaphore(2), 2, 0).generate(blocks(2), Client(), ignore_progress)
    assert result.cards == []
    assert result.success_blocks == 2
    assert not result.failed_blocks
    assert calls == 2


def blocks(count: int) -> list[TextBlock]:
    return [TextBlock(index, f"第 {index + 1} 页", str(index)) for index in range(count)]


async def test_concurrency_and_order_across_two_decks() -> None:
    active = peak = 0

    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.005 * (5 - int(text)))
                return card_json(f"卡片{text}")
            finally:
                active -= 1

    generator = CardGenerator(asyncio.Semaphore(3), 3, retry_delay=0)
    results = await asyncio.gather(*(generator.generate(blocks(5), Client(), ignore_progress) for _ in range(2)))
    assert peak == 3
    assert active == 0
    for result in results:
        assert [card.title for card in result.cards] == [f"卡片{i}" for i in range(5)]


async def test_rate_limit_switches_remaining_blocks_to_serial() -> None:
    calls: Counter = Counter()
    active = 0
    serial_active: list[int] = []

    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            nonlocal active
            calls[text] += 1
            if text == "0" and calls[text] <= 2:
                raise AIError("限流", retryable=True, degrade=True)
            active += 1
            try:
                if text != "1":
                    serial_active.append(active)
                await asyncio.sleep(0.01)
                return card_json(f"卡片{text}")
            finally:
                active -= 1

    progress: list[int] = []

    async def on_done(done: int, failures: list[FailedBlock]) -> None:
        progress.append(done)

    generator = CardGenerator(asyncio.Semaphore(2), 2, retry_delay=0)
    result = await generator.generate(blocks(6), Client(), on_done)
    assert len(result.cards) == 6
    assert not result.failed_blocks
    assert calls["0"] == 3
    assert all(count == 1 for key, count in calls.items() if key != "0")
    assert serial_active == [1] * 5
    assert progress == list(range(1, 7))


async def test_partial_json_failure_and_fenced_retry() -> None:
    calls: Counter = Counter()

    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            calls[text] += 1
            if text == "1" or (text == "0" and calls[text] == 1):
                return "这不是 JSON"
            return "```json\n" + card_json(f"卡片{text}") + "\n```"

    result = await CardGenerator(asyncio.Semaphore(3), 3, 0).generate(blocks(3), Client(), ignore_progress)
    assert [card.title for card in result.cards] == ["卡片0", "卡片2"]
    assert result.success_blocks == 2
    assert calls == {"0": 2, "1": 2, "2": 1}
    assert result.failed_blocks[0].block_index == 1
    assert "JSON" in result.failed_blocks[0].error


async def test_persistent_server_failure_has_bounded_attempts() -> None:
    calls: Counter = Counter()

    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            calls[text] += 1
            if text == "0":
                raise AIError("5xx", retryable=True, degrade=True)
            return card_json()

    result = await CardGenerator(asyncio.Semaphore(1), 1, 0).generate(blocks(3), Client(), ignore_progress)
    assert calls == {"0": 3, "1": 1, "2": 1}
    assert len(result.failed_blocks) == 1
    assert len(result.cards) == 2


async def test_cancellation_cleans_up_all_workers() -> None:
    active = 0

    class Client:
        async def complete(self, prompt: str, text: str) -> str:
            nonlocal active
            active += 1
            try:
                await asyncio.sleep(30)
                return card_json()
            finally:
                active -= 1

    task = asyncio.create_task(CardGenerator(asyncio.Semaphore(3), 3).generate(blocks(4), Client(), ignore_progress))
    await asyncio.sleep(0.01)
    assert active == 3
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0


@pytest.mark.parametrize("change", [
    {"correct_index": 4}, {"correct_index": True}, {"options": ["a", "b", "c"]},
    {"options": ["a", "a", "b", "c"]}, {"title": ""}, {"title": "长" * 17},
])
def test_invalid_card_schema(change: dict) -> None:
    data = json.loads(card_json())
    data[0].update(change)
    with pytest.raises(AIError, match="JSON"):
        parse_cards(json.dumps(data))
