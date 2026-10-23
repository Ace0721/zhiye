"""提纲生成不因排版和微小超限失败；等待必须能超时或停止。"""

import asyncio
import json
from io import BytesIO

import httpx
import pytest
from docx import Document

from app.main import create_app
from app.models import Deck, DeckSource
from app.services.ai_client import AIError
from app.services.study_ai import StudyAIManager, parse_output
from app.services.study_format import clean_text


MARKDOWN = """# 牛顿第二定律
先理解合力、质量和加速度之间的关系。
## 核心公式
- **F = ma**，必须使用合外力，并在惯性参考系下应用。
- F = ma，必须使用合外力，并在惯性参考系下应用。
> 来源：第2页/张｜合外力等于质量乘加速度
## 易混与边界
- 速度为零时，加速度不一定为零。
"""


def test_markdown_preserves_conditions_deduplicates_and_parses_refs():
    notes = parse_output(MARKDOWN,"notes")
    assert notes.title == "牛顿第二定律"
    assert notes.sections[0].bullets == ["F = ma，必须使用合外力，并在惯性参考系下应用。"]
    assert notes.sections[0].source_refs[0].page == 2
    assert "加速度不一定为零" in notes.pitfalls[0]
    assert parse_output('```markdown\n'+MARKDOWN+'```',"notes") == notes
    assert clean_text("2**3**4") == "2**3**4"


def test_json_compatibility_drops_bad_optional_metadata_without_losing_text():
    notes = parse_output(json.dumps({"data":{"title":"公式提纲","extra":"ignore","sections":[
        {"title":"基本关系","content":"F = ma；仅适用于惯性系。\n条件：质量保持不变。","source_refs":[{"page":"bad","quote":"bad"}]}]}}),"notes")
    assert len(notes.sections[0].bullets) == 2 and notes.sections[0].source_refs == []
    assert notes.overview == "" and notes.pitfalls == []


async def test_nonresponding_client_has_bounded_retry_and_stage(config,monkeypatch):
    async def no_delay(_seconds): pass
    monkeypatch.setattr("app.services.study_ai.asyncio.sleep",no_delay)
    config.ai_timeout = 0.02
    calls = 0
    stages = []
    class Client:
        async def complete(self,*args,**kwargs):
            nonlocal calls
            calls += 1
            await asyncio.Event().wait()
    manager = StudyAIManager(config,None,asyncio.Semaphore(1))
    with pytest.raises(AIError,match="未完成"):
        await asyncio.wait_for(manager._call(Client(),"提纲","课件正文","notes",stages.append),0.5)
    assert calls == 2 and any("第2次尝试" in stage for stage in stages)


async def test_stop_then_regenerate_markdown_and_export_word(config):
    app = create_app(config)
    started = asyncio.Event()
    class SlowClient:
        def __init__(self,*args): pass
        async def complete(self,*args,**kwargs):
            started.set()
            await asyncio.Event().wait()
        async def close(self): pass
    class GoodClient(SlowClient):
        async def complete(self,*args,**kwargs): return MARKDOWN
    async with app.router.lifespan_context(app):
        manager = app.state.study_manager; manager.client_factory = SlowClient
        with app.state.sessions.begin() as session:
            deck = Deck(title="物理",source_filename="test.pdf");session.add(deck);session.flush()
            session.add(DeckSource(deck_id=deck.id,text="原文：合外力等于质量乘加速度"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            path = f"/api/decks/{deck.id}/study/notes"
            assert (await client.post(path)).status_code == 202
            await asyncio.wait_for(started.wait(),0.5)
            state = (await client.get(path)).json()
            assert "生成精简提纲" in state["stage"] and state["elapsed_seconds"] is not None
            stopped = await client.post(path+"/cancel")
            assert stopped.json()["status"] == "failed" and "停止" in stopped.json()["error"]
            manager.client_factory = GoodClient
            await client.post(path)
            await asyncio.gather(*list(manager.running.values()))
            state = (await client.get(path)).json()
            assert state["status"] == "completed" and not state["data"]["sections"][0]["source_refs"]
            # 来源不存在就剔除引用，不猜页码，正文照常导出。
            exported = await client.get(f"/api/decks/{deck.id}/study.docx")
            text = "\n".join(p.text for p in Document(BytesIO(exported.content)).paragraphs)
            assert exported.status_code == 200 and "惯性参考系" in text and "**" not in text
            assert (await client.post('/api/decks/999/study/notes/cancel')).status_code == 404


async def test_cancel_before_task_starts_does_not_leave_queued_state(config):
    app = create_app(config)
    async with app.router.lifespan_context(app):
        manager = app.state.study_manager
        with app.state.sessions.begin() as session:
            deck = Deck(title="知识",source_filename="a.pdf");session.add(deck);session.flush()
            session.add(DeckSource(deck_id=deck.id,text="正文"))
        manager.submit(deck.id,"notes")
        assert (await manager.cancel(deck.id,"notes"))["status"] == "failed"


async def test_nonshrinking_long_source_stops_instead_of_repeating_forever(config):
    app = create_app(config)
    calls = 0
    class Client:
        def __init__(self,*args): pass
        async def complete(self,prompt,text,**kwargs):
            nonlocal calls
            calls += 1
            return text
        async def close(self): pass
    async with app.router.lifespan_context(app):
        manager = app.state.study_manager;manager.client_factory = Client
        with app.state.sessions.begin() as session:
            deck = Deck(title="长课件",source_filename="long.pdf");session.add(deck);session.flush()
            session.add(DeckSource(deck_id=deck.id,text="知识正文"*5000))
        manager.submit(deck.id,"notes")
        await asyncio.wait_for(asyncio.gather(*list(manager.running.values())),1)
        state = manager.snapshot(deck.id,"notes")
        assert state["status"] == "failed" and "未缩短原文" in state["error"] and calls == 3


async def test_cancel_notes_during_upload_keeps_successful_cards(config):
    from test_content_workflows import MockAI, configure
    app = create_app(config)
    started = asyncio.Event()
    class SlowNotes(MockAI):
        async def complete(self,prompt,text,**kwargs):
            started.set()
            await asyncio.Event().wait()
    async with app.router.lifespan_context(app):
        configure(app)
        app.state.study_manager.client_factory = SlowNotes
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            response = await client.post('/api/upload',files={"file":("a.pptx",b"mock")},data={"outputs":"cards,notes"})
            task_id = response.json()["task_id"]
            task = app.state.task_manager.running[task_id]
            await asyncio.wait_for(started.wait(),1)
            deck_id = app.state.task_manager.snapshot(task_id).deck_id
            await client.post(f'/api/decks/{deck_id}/study/notes/cancel')
            await asyncio.wait_for(task,2)
            state = app.state.task_manager.snapshot(task_id)
            assert state.status == "completed" and state.generated_outputs == ["cards"]
            assert "停止" in state.output_errors["notes"]
