import asyncio
import json
from io import BytesIO

import httpx
import pytest
from docx import Document

from app.main import create_app
from app.models import Deck, DeckSource, StudyArtifact
from app.schemas import RevisionNotes
from app.services.ai_client import AIError
from app.services.study_ai import parse_output


NOTES = {"title": "民事诉讼复习提纲", "overview": "围绕诉讼主体、举证与程序推进，理解权利如何获得救济。",
         "sections": [{"heading": "举证责任", "bullets": ["当事人对自己提出的主张提供证据；适用例外须依课件列明的条件。"]}],
         "pitfalls": ["提出主张与证明主张不是同一件事。"]}
MAP = {"title": "民事诉讼的运行逻辑", "overview": "从诉讼主体出发，通过证据与程序实现争议解决。", "branches": [
    {"label": "事实认定", "relation": "依赖", "detail": "法院以证据确定待证事实。", "children": [
        {"label": "举证责任", "relation": "分配责任", "detail": "明确谁需要为主张提供证明。", "children": []}]},
    {"label": "程序推进", "relation": "遵循", "detail": "程序约束争议的处理过程。", "children": [
        {"label": "起诉与受理", "relation": "始于", "detail": "符合起诉条件后进入审理程序。", "children": []}]}]}


def test_reject_flat_map_and_overlong_notes() -> None:
    flat = dict(MAP, branches=[dict(MAP["branches"][0], children=[])])
    with pytest.raises(AIError):
        parse_output(json.dumps(flat), "map")
    notes = dict(NOTES, sections=[{"heading": str(i), "bullets": ["长" * 100] * 4} for i in range(6)])
    with pytest.raises(AIError):
        parse_output(json.dumps(notes), "notes")
    assert parse_output("```json\n" + json.dumps(NOTES) + "\n```", "notes").title == NOTES["title"]


async def test_distinct_ai_calls_cached_results_and_word(config) -> None:
    app = create_app(config)
    calls = []

    class Client:
        def __init__(self, *args): pass
        async def complete(self, prompt, text, **kwargs):
            calls.append((prompt, text))
            return json.dumps(MAP if "思维导图" in prompt else NOTES)
        async def close(self): pass

    async with app.router.lifespan_context(app):
        manager = app.state.study_manager
        manager.client_factory = Client
        with app.state.sessions.begin() as session:
            deck = Deck(title="民事诉讼", source_filename="test.pptx")
            session.add(deck); session.flush()
            session.add(DeckSource(deck_id=deck.id, text="真实正文：举证责任与程序。"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(f"/api/decks/{deck.id}/study/map")).json()["status"] == "idle"
            for kind in ("notes", "map"):
                assert (await client.post(f"/api/decks/{deck.id}/study/{kind}")).status_code == 202
                # 重复点击不增加请求，Word 与导图相互独立。
                await client.post(f"/api/decks/{deck.id}/study/{kind}")
                await asyncio.gather(*list(manager.running.values()))
                state = (await client.get(f"/api/decks/{deck.id}/study/{kind}")).json()
                assert state["status"] == "completed" and state["progress"] == 100
                assert state["source_type"] == "course_text"
            word = await client.get(f"/api/decks/{deck.id}/study.docx")
            assert word.status_code == 200
            text = "\n".join(p.text for p in Document(BytesIO(word.content)).paragraphs)
            assert "举证责任" in text and "易混与边界" in text
            assert "知识点简明解释" not in text
            await client.get(f"/api/decks/{deck.id}/study/notes")
            assert len(calls) == 2
            assert all("真实正文" in source for _, source in calls)
            assert (await client.post("/api/decks/999/study/map")).status_code == 404
            assert (await client.post(f"/api/decks/{deck.id}/study/unknown")).status_code == 422
        with app.state.sessions.begin() as session:
            session.add(StudyArtifact(deck_id=deck.id, kind="test", status="generating", source_type="course_text"))
        manager.recover()
        with app.state.sessions() as session:
            assert session.query(StudyArtifact).filter_by(kind="test").one().status == "failed"
            assert session.query(StudyArtifact).filter_by(kind="notes").one().status == "completed"


async def test_long_input_preserves_tail_and_limits_concurrency(config) -> None:
    app = create_app(config)
    active = peak = 0
    inputs = []

    class Client:
        def __init__(self, *args): pass
        async def complete(self, prompt, text, **kwargs):
            nonlocal active, peak
            inputs.append(text)
            active += 1; peak = max(peak, active)
            try:
                await asyncio.sleep(0.005)
                return json.dumps(NOTES) if "严格JSON对象" in prompt else "压缩后的概念骨架"
            finally:
                active -= 1
        async def close(self): pass

    async with app.router.lifespan_context(app):
        manager = app.state.study_manager
        manager.client_factory = Client
        with app.state.sessions.begin() as session:
            deck = Deck(title="长课件", source_filename="long.pdf")
            session.add(deck); session.flush()
            session.add(DeckSource(deck_id=deck.id, text="知识正文" * 9000 + "末尾重要公式"))
        manager.submit(deck.id, "notes")
        await asyncio.gather(*list(manager.running.values()))
        assert manager.snapshot(deck.id, "notes")["status"] == "completed"
        assert any("末尾重要公式" in text for text in inputs)
        assert peak <= config.ai_concurrency


async def test_invalid_json_retries_once(config, monkeypatch) -> None:
    async def no_delay(_seconds): pass
    monkeypatch.setattr("app.services.study_ai.asyncio.sleep", no_delay)
    app = create_app(config)
    calls = 0

    class Client:
        def __init__(self, *args): pass
        async def complete(self, prompt, text, **kwargs):
            nonlocal calls
            calls += 1
            return "not JSON" if calls == 1 else json.dumps(NOTES)
        async def close(self): pass

    async with app.router.lifespan_context(app):
        manager = app.state.study_manager
        manager.client_factory = Client
        with app.state.sessions.begin() as session:
            deck = Deck(title="知识", source_filename="a.pdf")
            session.add(deck); session.flush()
            session.add(DeckSource(deck_id=deck.id, text="知识正文"))
        manager.submit(deck.id, "notes")
        await asyncio.gather(*list(manager.running.values()))
        assert calls == 2 and manager.snapshot(deck.id, "notes")["status"] == "completed"


async def test_auth_failure_is_persisted_and_no_fake_document_is_returned(config) -> None:
    app = create_app(config)
    calls = 0

    class Client:
        def __init__(self, *args): pass
        async def complete(self, prompt, text, **kwargs):
            nonlocal calls
            calls += 1
            raise AIError("AI 认证失败或无访问权限，请检查 API Key")
        async def close(self): pass

    async with app.router.lifespan_context(app):
        manager = app.state.study_manager
        manager.client_factory = Client
        with app.state.sessions.begin() as session:
            deck = Deck(title="知识", source_filename="a.pdf")
            session.add(deck); session.flush()
            session.add(DeckSource(deck_id=deck.id, text="知识正文"))
        manager.submit(deck.id, "notes")
        await asyncio.gather(*list(manager.running.values()))
        state = manager.snapshot(deck.id, "notes")
        assert calls == 1 and state["status"] == "failed"
        assert "认证失败" in state["error"] and state["data"] is None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(f"/api/decks/{deck.id}/study.docx")).status_code == 409
