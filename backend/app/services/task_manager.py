"""单进程后台任务：内存管理生命周期，SQLite 保存可查询状态。"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from threading import Event
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Card, Deck, Task, utcnow
from app.schemas import FailedBlock, TaskResponse
from app.services.ai_client import AIClient, AIConfig, AIError, resolve_ai_config
from app.services.card_gen import CardGenerator, GenerationResult
from app.services.parser import ParseError, TextBlock, parse_document

ACTIVE_STATUSES = ("queued", "parsing", "generating")


class TaskManager:
    def __init__(self, config: Settings, sessions: sessionmaker[Session],
                 client_factory: Callable[[AIConfig, int], AIClient] = AIClient,
                 parser: Callable[[Path, Event | None], list[TextBlock]] = parse_document) -> None:
        self.config = config
        self.sessions = sessions
        self.client_factory = client_factory
        self.parser = parser
        self.running: dict[str, asyncio.Task[None]] = {}
        self.states: dict[str, TaskResponse] = {}
        self.generator = CardGenerator(asyncio.Semaphore(config.ai_concurrency), config.ai_concurrency)
        self.upload_dir = config.data_dir / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def recover(self) -> None:
        """每次服务启动终结遗留任务，清理本应用创建的临时上传文件。"""
        with self.sessions.begin() as session:
            session.execute(update(Task).where(Task.status.in_(ACTIVE_STATUSES)).values(
                status="failed", error="服务已重启，任务中断，请重新上传课件", updated_at=utcnow()))
        for path in self.upload_dir.glob("upload-*"):
            if path.is_file():
                path.unlink(missing_ok=True)

    def submit(self, path: Path, filename: str) -> str:
        """先持久化任务，再持有后台协程引用；不等待 AI。"""
        task_id = str(uuid4())
        with self.sessions.begin() as session:
            session.add(Task(id=task_id))
        state = self.snapshot(task_id)
        if state is not None:
            self.states[task_id] = state
        deadline = asyncio.get_running_loop().time() + self.config.task_timeout
        task = asyncio.create_task(self._run(task_id, path, filename, deadline), name=f"zhiye-{task_id}")
        self.running[task_id] = task

        def discard(_task: asyncio.Task[None]) -> None:
            self.running.pop(task_id, None)
            self.states.pop(task_id, None)
            # 提取异常以避免无人读取的任务异常；不打印可能敏感的异常内容。
            if not _task.cancelled():
                _task.exception()

        task.add_done_callback(discard)
        return task_id

    def snapshot(self, task_id: str) -> TaskResponse | None:
        with self.sessions() as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            count = session.scalar(select(func.count(Card.id)).where(Card.deck_id == task.deck_id)) if task.deck_id else 0
            return TaskResponse(status=task.status, progress=task.progress,
                                total_blocks=task.total_blocks, done_blocks=task.done_blocks,
                                error=task.error, deck_id=task.deck_id, card_count=count or 0,
                                failed_blocks=json.loads(task.failed_blocks_json))

    def _update(self, task_id: str, **values: object) -> None:
        # 本地短事务不跨 await 持有，也不在同一会话中访问并发 AI 请求。
        with self.sessions.begin() as session:
            session.execute(update(Task).where(Task.id == task_id).values(**values, updated_at=utcnow()))
        state = self.snapshot(task_id)
        if state is not None:
            self.states[task_id] = state

    def _finish(self, task_id: str, filename: str, result: GenerationResult) -> None:
        """卡片和任务完成状态在同一事务提交，防止产生半成品卡组。"""
        with self.sessions.begin() as session:
            deck = Deck(title=Path(filename).stem, source_filename=filename)
            session.add(deck)
            session.flush()
            for index, card in enumerate(result.cards):
                values = card.model_dump(exclude={"options"})
                session.add(Card(deck_id=deck.id, order_index=index,
                                 options_json=json.dumps(card.options, ensure_ascii=False), **values))
            task = session.get(Task, task_id)
            if task is None:
                raise RuntimeError("任务记录不存在")
            task.deck_id = deck.id
            task.status = "completed"
            task.progress = 100
            task.error = None
            task.failed_blocks_json = json.dumps([block.model_dump() for block in result.failed_blocks], ensure_ascii=False)
            task.updated_at = utcnow()

    async def _run(self, task_id: str, path: Path, filename: str, deadline: float) -> None:
        cancel = Event()
        client: AIClient | None = None

        def parse_and_cleanup() -> list[TextBlock]:
            try:
                return self.parser(path, cancel)
            finally:
                path.unlink(missing_ok=True)

        try:
            async with asyncio.timeout_at(deadline):
                self._update(task_id, status="parsing", progress=1)
                blocks = await asyncio.to_thread(parse_and_cleanup)
                self._update(task_id, status="generating", progress=5, total_blocks=len(blocks))
                with self.sessions() as session:
                    ai_config = resolve_ai_config(session, self.config)
                client = self.client_factory(ai_config, self.config.ai_timeout)

                async def on_done(done: int, failures: list[FailedBlock]) -> None:
                    self._update(task_id, done_blocks=done, progress=5 + int(90 * done / len(blocks)),
                                 failed_blocks_json=json.dumps([block.model_dump() for block in failures], ensure_ascii=False))

                result = await self.generator.generate(blocks, client, on_done)
                if not result.cards:
                    message = "所有文本块均未能生成卡片，请检查 AI 配置后重新上传"
                    if not result.failed_blocks:
                        message = "课件文本不足以生成知识卡，AI 返回了空数组，请换一份含知识点的课件"
                    elif result.failed_blocks:
                        message += "；" + result.failed_blocks[0].error
                    raise AIError(message)
            # 生成结束后执行一次短事务，中间没有可取消的 await。
            self._finish(task_id, filename, result)
        except TimeoutError:
            self._update(task_id, status="failed", error="整体任务超时，请减少课件大小或调大 ZHIYE_TASK_TIMEOUT")
        except asyncio.CancelledError:
            self._update(task_id, status="failed", error="服务正在关闭，任务中断，请重新上传课件")
            raise
        except (AIError, ParseError) as exc:
            self._update(task_id, status="failed", error=str(exc))
        except Exception:
            self._update(task_id, status="failed", error="任务处理失败，请检查本地数据目录权限和可用空间后重试")
        finally:
            cancel.set()
            if client is not None:
                try:
                    async with asyncio.timeout(5):
                        await client.close()
                except Exception:
                    pass
            # 若解析线程尚在读取文件，它会在退出时自行清理。
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    async def shutdown(self) -> None:
        """关闭时取消并等待后台任务，不遗留生成协程。"""
        tasks = list(self.running.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
