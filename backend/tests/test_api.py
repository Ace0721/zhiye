import asyncio
import time
from pathlib import Path

import httpx
import openai
import pytest

from app.config import Settings
from app.main import create_app
from app.routers import upload as upload_router
from app.services.ai_client import AIClient, AIConfig, AIError
from conftest import card_json
from test_parser import make_pdf


async def wait_terminal(client: httpx.AsyncClient, task_id: str) -> dict:
    for _ in range(200):
        response = await client.get(f"/api/tasks/{task_id}")
        response.raise_for_status()
        task = response.json()
        if task["status"] in {"completed", "failed"}:
            return task
        await asyncio.sleep(0.01)
    pytest.fail("任务未按时结束")


async def test_twenty_page_pdf_upload_poll_and_cards(config: Settings, tmp_path: Path) -> None:
    path = tmp_path / "lecture.pdf"
    make_pdf(path, 20)
    application = create_app(config)
    gate = asyncio.Event()

    class MockClient:
        def __init__(self, *_args) -> None:
            pass

        async def complete(self, prompt: str, text: str) -> str:
            await gate.wait()
            return card_json("牛顿第二定律")

        async def close(self) -> None:
            pass

    async with application.router.lifespan_context(application):
        application.state.task_manager.client_factory = MockClient
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            assert (await client.get("/api/health")).json() == {"status": "ok"}
            started = time.monotonic()
            response = await client.post("/api/upload", files={"file": ("lecture.PDF", path.read_bytes(), "application/pdf")})
            assert response.status_code == 202
            assert time.monotonic() - started < 5
            task_id = response.json()["task_id"]
            # AI 尚未响应时，上传响应和进度查询都可完成。
            for _ in range(100):
                state = (await client.get(f"/api/tasks/{task_id}")).json()
                if state["status"] == "generating":
                    break
                await asyncio.sleep(0.01)
            assert state["status"] == "generating" and state["progress"] > 0
            assert state["done_blocks"] == 0
            gate.set()
            result = await wait_terminal(client, task_id)
            assert result["status"] == "completed"
            assert result["done_blocks"] == result["total_blocks"] >= 3
            cards = (await client.get(f"/api/decks/{result['deck_id']}/cards")).json()
            assert len(cards) == result["card_count"]
            assert [card["order_index"] for card in cards] == list(range(len(cards)))
            assert len(cards[0]["options"]) == 4
            assert not list(application.state.task_manager.upload_dir.iterdir())


async def test_upload_validation_and_missing_resources(config: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    application = create_app(config)
    monkeypatch.setattr(upload_router, "MAX_UPLOAD_BYTES", 100)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            for filename, content, expected in [("a.txt", b"text", 415), ("a.pdf", b"", 400), ("a.pdf", b"x" * 101, 413)]:
                response = await client.post("/api/upload", files={"file": (filename, content)})
                assert response.status_code == expected
                assert response.json()["detail"]
            assert (await client.get("/api/tasks/missing")).status_code == 404
            assert (await client.get("/api/decks/999/cards")).status_code == 404
            assert not list(application.state.task_manager.upload_dir.iterdir())


async def test_corrupt_upload_is_reported_as_failed(config: Settings) -> None:
    application = create_app(config)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post("/api/upload", files={"file": ("bad.pdf", b"not pdf")})
            assert response.status_code == 202
            result = await wait_terminal(client, response.json()["task_id"])
            assert result["status"] == "failed"
            assert "解析失败" in result["error"]


@pytest.mark.parametrize("status, expected, transient", [
    (401, "认证失败", False), (403, "认证失败", False), (404, "不存在", False),
    (429, "限流", True), (500, "5xx", True), (400, "HTTP 400", False),
])
async def test_sdk_error_mapping_and_redaction(status: int, expected: str, transient: bool) -> None:
    key = "test-sensitive-value"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": f"server echoed {key}"}})

    ai = AIClient(AIConfig("https://example.invalid/v1", key, "mock-model"), 10)
    await ai.client.close()
    ai.client = openai.AsyncOpenAI(
        api_key=key, base_url="https://example.invalid/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(AIError, match=expected) as captured:
            await ai.complete("prompt", "text")
        assert key not in str(captured.value)
        assert captured.value.retryable is transient
        assert captured.value.degrade is transient
    finally:
        await ai.close()


@pytest.mark.parametrize("failure", ["network", "timeout"])
async def test_sdk_network_errors_are_friendly(failure: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ConnectError("private details", request=request)
        raise httpx.ReadTimeout("private details", request=request)

    ai = AIClient(AIConfig("https://example.invalid/v1", "test", "model"), 1)
    await ai.client.close()
    ai.client = openai.AsyncOpenAI(
        api_key="test", base_url="https://example.invalid/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(AIError, match="连接|超时") as captured:
            await ai.complete("prompt", "text")
        assert captured.value.retryable
        assert "private" not in str(captured.value)
    finally:
        await ai.close()


async def test_sdk_reports_truncated_output_without_echoing_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id":"test","object":"chat.completion","created":0,"model":"test",
            "choices":[{"index":0,"finish_reason":"length","message":{"role":"assistant","content":"private truncated output"}}]})
    ai = AIClient(AIConfig("https://example.invalid/v1", "test", "model"), 1)
    await ai.client.close()
    ai.client = openai.AsyncOpenAI(api_key="test", base_url="https://example.invalid/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(AIError, match="截断") as caught:
            await ai.complete("prompt", "text", max_tokens=5000)
        assert caught.value.retryable and "private" not in str(caught.value)
    finally:
        await ai.close()
