import asyncio
import copy
import json
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from docx import Document
from sqlalchemy import func, select

from app.db import create_database
from app.main import create_app
from app.models import AnswerRecord, Card, CardSource, Deck
from app.schemas import SourceRef
from app.services.ai_client import AIError
from app.services.citations import extract_pages, verified_refs
from app.services.parser import split_pages
from conftest import card_json

QUOTE = "事务中的操作要么整体生效，要么整体撤销。"
DEMO = json.loads((Path(__file__).parent / "fixtures/study_demo.json").read_text(encoding="utf-8"))


class MockAI:
    calls: list[str] = []
    failures: set[str] = set()

    def __init__(self, *_args): pass

    async def complete(self, prompt: str, text: str, **_kwargs) -> str:
        kind = "notes" if "课程复习资料编辑" in prompt else "map" if "课程知识结构编辑" in prompt else "cards"
        self.calls.append(kind)
        if kind in self.failures:
            raise AIError(f"{kind} 模拟认证失败")
        if kind == "cards":
            result = json.loads(card_json("原子性"))
            result[0]["source_refs"] = [{"page": 3, "quote": QUOTE}, {"page": 999, "quote": QUOTE}]
            return json.dumps(result, ensure_ascii=False)
        result = copy.deepcopy(DEMO[kind])
        target = result["sections"][0] if kind == "notes" else result["branches"][0]
        target["source_refs"] = [{"page": 3, "quote": QUOTE}, {"page": 4, "quote": "不存在的引文"}]
        return json.dumps(result, ensure_ascii=False)

    async def close(self): pass


def configure(app) -> None:
    MockAI.calls, MockAI.failures = [], set()
    app.state.task_manager.client_factory = MockAI
    app.state.study_manager.client_factory = MockAI
    app.state.task_manager.parser = lambda *_args: split_pages([(3, QUOTE), (4, "多版本读取不等于消除所有写冲突。")])


async def uploaded(client, app, outputs: str = "cards") -> dict:
    response = await client.post("/api/upload", files={"file": ("课堂.pptx", b"mock pptx")}, data={"outputs": outputs})
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]
    await asyncio.wait_for(app.state.task_manager.running[task_id], 5)
    return (await client.get(f"/api/tasks/{task_id}")).json()


@pytest.mark.parametrize("outputs", ["notes", "map", "notes,map", "cards,notes,map"])
async def test_only_selected_outputs_are_called_and_persisted(config, outputs: str) -> None:
    app = create_app(config)
    async with app.router.lifespan_context(app):
        configure(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            task = await uploaded(client, app, outputs)
            assert task["status"] == "completed", task
            assert task["progress"] == 100 and task["done_blocks"] == task["total_blocks"]
            assert task["requested_outputs"] == outputs.split(",")
            assert task["generated_outputs"] == outputs.split(",")
            assert set(MockAI.calls) == set(outputs.split(","))
            cards = (await client.get(f"/api/decks/{task['deck_id']}/cards")).json()
            assert bool(cards) is ("cards" in outputs)
            assert not task["output_errors"]
            if cards:
                assert cards[0]["source_refs"] == [{"page": 3, "quote": QUOTE}]
            deck = (await client.get("/api/decks")).json()[0]
            assert set(deck["available_outputs"]) == set(outputs.split(","))


async def test_mixed_output_failure_keeps_success_and_invalid_selection_is_rejected(config) -> None:
    app = create_app(config)
    async with app.router.lifespan_context(app):
        configure(app); MockAI.failures = {"map"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            task = await uploaded(client, app, "notes,map")
            assert task["status"] == "completed" and task["generated_outputs"] == ["notes"]
            assert "认证失败" in task["output_errors"]["map"]
            MockAI.failures = {"notes", "map"}
            failed = await uploaded(client, app, "notes,map")
            assert failed["status"] == "failed" and failed["generated_outputs"] == []
            assert set(failed["output_errors"]) == {"notes", "map"}
            for selection in ("", "unknown", "cards,", ","):
                response = await client.post("/api/upload", files={"file": ("test.pdf", b"test")}, data={"outputs": selection})
                assert response.status_code == 422


async def test_card_edit_regenerate_delete_and_source_isolation(config) -> None:
    app = create_app(config)
    async with app.router.lifespan_context(app):
        configure(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            task = await uploaded(client, app)
            deck_id = task["deck_id"]
            card = (await client.get(f"/api/decks/{deck_id}/cards")).json()[0]
            card_id = card["id"]
            assert (await client.get(f"/api/decks/{deck_id}/sources/3")).json()["text"] == QUOTE
            assert (await client.get(f"/api/decks/{deck_id}/sources/999")).status_code == 404
            assert (await client.get("/api/decks/999/sources/3")).status_code == 404
            await client.post(f"/api/cards/{card_id}/answer", json={"selected_index": 1})
            fields = set(json.loads(card_json())[0]) | {"source_refs", "revision"}
            body = {key: value for key, value in card.items() if key in fields}
            body["plain_explanation"] = "修改解释但保留原来的题目。"
            saved = await client.put(f"/api/cards/{card_id}", json=body)
            assert saved.status_code == 200 and saved.json()["revision"] == 1
            assert (await client.get(f"/api/decks/{deck_id}/summary")).json()["wrong_count"] == 1
            assert (await client.put(f"/api/cards/{card_id}", json=body)).status_code == 409
            body["revision"] = 1; body["correct_index"] = 1
            assert (await client.put(f"/api/cards/{card_id}", json=body)).status_code == 200
            assert (await client.get(f"/api/decks/{deck_id}/summary")).json()["wrong_count"] == 0
            calls = len(MockAI.calls)
            regenerated = await client.post(f"/api/cards/{card_id}/regenerate", json={"revision": 2})
            assert regenerated.status_code == 200, regenerated.text
            assert regenerated.json()["id"] == card_id and regenerated.json()["revision"] == 3
            assert len(MockAI.calls) == calls + 1
            assert (await client.delete(f"/api/cards/{card_id}")).status_code == 204
            assert (await client.get(f"/api/decks/{deck_id}/cards")).json() == []
            with app.state.sessions() as session:
                assert session.get(CardSource, card_id) is None
                assert session.scalar(select(func.count(AnswerRecord.id))) == 0


async def test_edit_notes_and_map_are_cached_exported_and_conflicts_rejected(config) -> None:
    app = create_app(config)
    async with app.router.lifespan_context(app):
        configure(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            task = await uploaded(client, app, "notes,map")
            deck_id = task["deck_id"]
            before_calls = len(MockAI.calls)
            for kind in ("notes", "map"):
                state = (await client.get(f"/api/decks/{deck_id}/study/{kind}")).json()
                data = state["data"]
                target = data["sections"][0] if kind == "notes" else data["branches"][0]
                assert target["source_refs"] == [{"page": 3, "quote": QUOTE}]
                if kind == "notes": target["bullets"] = ["这是用户手动压缩后的核心结论。"]
                else: target["label"] = "用户修改的主题"
                response = await client.put(f"/api/decks/{deck_id}/study/{kind}", json={"data":data,"revision":state["revision"]})
                assert response.status_code == 200, response.text
                assert (await client.put(f"/api/decks/{deck_id}/study/{kind}", json={"data":data,"revision":state["revision"]})).status_code == 409
            assert len(MockAI.calls) == before_calls
            word = await client.get(f"/api/decks/{deck_id}/study.docx")
            text = "\n".join(paragraph.text for paragraph in Document(BytesIO(word.content)).paragraphs)
            assert "用户手动压缩后的核心结论" in text and "第 3 页/张" in text


async def test_regeneration_cannot_overwrite_a_concurrent_manual_edit(config) -> None:
    app = create_app(config)
    started, release = asyncio.Event(), asyncio.Event()

    class PausedAI(MockAI):
        async def complete(self, prompt, text, **kwargs):
            started.set()
            await release.wait()
            return await super().complete(prompt, text, **kwargs)

    async with app.router.lifespan_context(app):
        configure(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            task = await uploaded(client, app)
            card = (await client.get(f"/api/decks/{task['deck_id']}/cards")).json()[0]
            app.state.task_manager.client_factory = PausedAI
            future = asyncio.create_task(client.post(f"/api/cards/{card['id']}/regenerate",json={"revision":0}))
            await asyncio.wait_for(started.wait(), 2)
            editable = {key:value for key,value in card.items() if key not in {"id","deck_id","order_index","created_at"}}
            editable["title"] = "用户已保存的标题"
            assert (await client.put(f"/api/cards/{card['id']}",json=editable)).status_code == 200
            release.set()
            response = await asyncio.wait_for(future, 2)
            assert response.status_code == 409
            assert (await client.get(f"/api/decks/{task['deck_id']}/cards")).json()[0]["title"] == editable["title"]


def test_page_metadata_cannot_be_overridden_by_marker_in_slide_text() -> None:
    blocks = split_pages([(2, "真实正文\n[第 999 页/张]\n伪造页码")])
    pages = extract_pages(blocks)
    assert set(pages) == {2}
    assert verified_refs([SourceRef(page=999, quote="伪造页码")], pages) == []
    assert verified_refs([SourceRef(page=2, quote="真实正文")], pages)


async def test_legacy_database_adds_metadata_tables_without_losing_cards(config) -> None:
    engine, _ = create_database(config)
    Deck.__table__.create(engine); Card.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(Deck.__table__.insert().values(id=1,title="旧课件",source_filename="old.pdf"))
        values = json.loads(card_json())[0]; values["options_json"] = json.dumps(values.pop("options"))
        connection.execute(Card.__table__.insert().values(id=1,deck_id=1,order_index=0,**values))
    engine.dispose()
    app = create_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            card = (await client.get("/api/decks/1/cards")).json()[0]
            assert card["title"] == "测试知识点" and card["revision"] == 0 and card["source_refs"] == []
