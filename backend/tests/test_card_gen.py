import asyncio
import json
from collections import Counter

import pytest

from app.schemas import FailedBlock
from app.services.ai_client import AIError
from app.services.card_gen import CardGenerator, parse_cards
from app.services.parser import TextBlock
from conftest import card_json


async def ignore_progress(done: int, failures: list[FailedBlock]) -> None:
    pass


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
