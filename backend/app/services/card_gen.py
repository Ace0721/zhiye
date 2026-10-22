"""并发生成、有限重试和串行补跑，按来源顺序返回结果。"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from app.schemas import FailedBlock, GeneratedCard
from app.services.ai_client import AIError
from app.services.parser import TextBlock

CARD_LIST = TypeAdapter(list[GeneratedCard])
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "card_gen.txt"


class CompletionClient(Protocol):
    async def complete(self, prompt: str, text: str) -> str: ...


def parse_cards(content: str) -> list[GeneratedCard]:
    """只移除包裹整个响应的 Markdown 围栏，不从解释文字中猜测 JSON。"""
    clean = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", clean, flags=re.DOTALL | re.IGNORECASE)
    if match:
        clean = match.group(1).strip()
    try:
        # 使用标准 JSON 解析，再执行严格字段校验。
        value = json.loads(clean)
        return CARD_LIST.validate_python(value)
    except (ValueError, ValidationError):
        raise AIError("AI 返回的内容不是合法知识卡 JSON，或字段不符合要求", retryable=True) from None


@dataclass
class GenerationResult:
    cards: list[GeneratedCard]
    failed_blocks: list[FailedBlock]
    success_blocks: int


class CardGenerator:
    def __init__(self, semaphore: asyncio.Semaphore, concurrency: int, retry_delay: float = 1.0) -> None:
        self.semaphore = semaphore
        self.concurrency = concurrency
        self.retry_delay = retry_delay

    async def _generate(self, client: CompletionClient, prompt: str, block: TextBlock,
                        attempts: int) -> list[GeneratedCard]:
        for attempt in range(attempts):
            try:
                # 退避时释放全局并发槽位，不阻塞其他课件。
                async with self.semaphore:
                    response = await client.complete(prompt, block.text)
                return parse_cards(response)
            except AIError as exc:
                if not exc.retryable or attempt + 1 == attempts:
                    raise
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
        raise RuntimeError("生成重试状态异常")

    async def generate(self, blocks: list[TextBlock], client: CompletionClient,
                       on_done: Callable[[int, list[FailedBlock]], Awaitable[None]]) -> GenerationResult:
        """限流重试耗尽后停止派发新块，收尾并发请求，再串行补跑。"""
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        results: dict[int, list[GeneratedCard]] = {}
        failures: dict[int, FailedBlock] = {}
        retry_indices: set[int] = set()
        degraded = asyncio.Event()
        progress_lock = asyncio.Lock()
        cursor = 0
        done = 0

        async def finalize(index: int, error: AIError | None = None) -> None:
            nonlocal done
            async with progress_lock:
                if error is not None:
                    failures[index] = FailedBlock(block_index=blocks[index].index,
                                                   source=blocks[index].source, error=str(error))
                done += 1
                await on_done(done, [failures[key] for key in sorted(failures)])

        async def worker() -> None:
            nonlocal cursor
            while cursor < len(blocks) and not degraded.is_set():
                index = cursor
                cursor += 1
                try:
                    results[index] = await self._generate(client, prompt, blocks[index], 2)
                except AIError as exc:
                    if exc.degrade:
                        degraded.set()
                        retry_indices.add(index)
                        continue
                    await finalize(index, exc)
                else:
                    await finalize(index)

        workers = [asyncio.create_task(worker()) for _ in range(min(self.concurrency, len(blocks)))]
        try:
            await asyncio.gather(*workers)
            pending = sorted(retry_indices | set(range(cursor, len(blocks))))
            for index in pending:
                try:
                    # 已重试过的块只补跑一次；未发送的块仍允许一次重试。
                    attempts = 1 if index in retry_indices else 2
                    results[index] = await self._generate(client, prompt, blocks[index], attempts)
                except AIError as exc:
                    await finalize(index, exc)
                else:
                    await finalize(index)
        finally:
            # 任务超时或取消时回收所有子任务，避免后台继续消耗 API 额度。
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        return GenerationResult(
            cards=[card for index in sorted(results) for card in results[index]],
            failed_blocks=[failures[index] for index in sorted(failures)],
            success_blocks=len(results),
        )
