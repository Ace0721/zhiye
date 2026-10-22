"""学习现场、历史数据统计与课件标签的回归测试。"""

import json
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.main import create_app
from app.models import AnswerRecord, Card, CardSource, Deck, LearningSession


def seed(application) -> tuple[int, int, list[int]]:
    with application.state.sessions.begin() as session:
        decks = [Deck(title="高等数学", source_filename="高数.pdf"), Deck(title="物理提纲", source_filename="physics.pptx")]
        session.add_all(decks); session.flush()
        cards = [Card(deck_id=decks[0].id, order_index=i, title=f"知识点{i}", plain_explanation="解释", key_point="重点",
                      question=f"问题{i}", options_json=json.dumps(["A", "B", "C", "D"]), correct_index=0, reexplain="再次解释") for i in range(2)]
        session.add_all(cards); session.flush()
        return decks[0].id, decks[1].id, [card.id for card in cards]


async def test_resume_retry_wrong_queue_restart_and_completion(config):
    app = create_app(config)
    async with app.router.lifespan_context(app):
        deck, _, ids = seed(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/decks/{deck}/session"
            state = (await client.post(path, json={})).json()
            assert len(state["queue"]) == 2 and state["index"] == 0
            stale = dict(revision=state["revision"], index=0, selected_index=1)
            state = (await client.post(path+"/all/answer", json=stale)).json()
            assert len(state["queue"]) == 3 and not state["answers"]["0"]["is_correct"]
            assert (await client.post(path+"/all/answer", json=stale)).status_code == 409
            state = (await client.put(path+"/all", json=dict(revision=state["revision"], index=1))).json()
            restored = (await client.post(path, json={})).json()
            assert restored == state
            assert (await client.put(path+"/all", json=dict(revision=state["revision"], index=2))).status_code == 422
            for index in [1, 2]:
                state = (await client.post(path+"/all/answer", json=dict(revision=state["revision"], index=index, selected_index=0))).json()
                state = (await client.put(path+"/all", json=dict(revision=state["revision"], index=min(index+1,2), completed=index==2))).json()
            assert state["completed"]
            wrong = (await client.post(path, json={"mode":"wrong"})).json()
            assert len(wrong["queue"]) == 1 and wrong["queue"][0]["id"] == ids[0]
            assert (await client.post(path, json={})).json()["completed"]
            restarted = (await client.post(path,json={"restart":True})).json()
            assert restarted["answers"] == {} and len(restarted["queue"]) == 2
        with app.state.sessions() as session:
            assert session.scalar(select(func.count(AnswerRecord.id))) == 3
    # 新应用实例仍从同一 SQLite 恢复，不依赖浏览器缓存或内存。
    second = create_app(config)
    async with second.router.lifespan_context(second):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second),base_url="http://test") as client:
            assert (await client.post(path,json={"mode":"wrong"})).json()["queue"][0]["id"] == ids[0]


async def test_session_reconciles_edited_and_deleted_cards(config):
    app = create_app(config)
    async with app.router.lifespan_context(app):
        deck, _, ids = seed(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            path=f"/api/decks/{deck}/session"
            state=(await client.post(path,json={})).json()
            state=(await client.post(path+"/all/answer",json=dict(revision=state["revision"],index=0,selected_index=0))).json()
            with app.state.sessions.begin() as session:
                card=session.get(Card,ids[0]);card.title="润色标题";card.provenance=CardSource(revision=1)
            state=(await client.post(path,json={})).json()
            assert "0" in state["answers"]
            with app.state.sessions.begin() as session:
                card=session.get(Card,ids[0]);card.question="新题目";card.provenance.revision+=1
            state=(await client.post(path,json={})).json()
            assert state["answers"] == {} and state["index"] == 0
            await client.delete(f"/api/cards/{ids[0]}")
            state=(await client.post(path,json={})).json()
            assert len(state["queue"]) == 1 and state["initial_count"] == 1 and state["queue"][0]["id"] == ids[1]


async def test_library_unique_counts_timezone_labels_and_resume(config, monkeypatch):
    monkeypatch.setattr("app.routers.learning.utcnow",lambda: datetime(2026,10,22,17,0,tzinfo=timezone.utc))
    app=create_app(config)
    async with app.router.lifespan_context(app):
        deck, other, ids=seed(app)
        with app.state.sessions.begin() as session:
            session.add_all([AnswerRecord(card_id=ids[0],selected_index=1,is_correct=False,created_at=datetime(2026,10,22,16,30,tzinfo=timezone.utc)),
                             AnswerRecord(card_id=ids[0],selected_index=0,is_correct=True,created_at=datetime(2026,10,22,16,40,tzinfo=timezone.utc)),
                             AnswerRecord(card_id=ids[1],selected_index=0,is_correct=True,created_at=datetime(2026,10,20,8,0,tzinfo=timezone.utc))])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            await client.post(f"/api/decks/{deck}/session",json={})
            tags=await client.put(f"/api/decks/{deck}/tags",json={"tags":[" 期末 ","高数","期末",""]})
            assert tags.json()["tags"] == ["期末","高数"]
            data=(await client.get('/api/library?offset_minutes=480')).json()
            assert data["stats"] == dict(deck_count=2,card_count=2,learned_count=2,wrong_count=1,today_count=1)
            assert data["activity"][-1] == {"date":"2026-10-23","count":1}
            assert data["resume"]["deck_id"] == deck
            assert next(row for row in data["decks"] if row["id"] == other)["card_count"] == 0
            assert next(row for row in data["decks"] if row["id"] == deck)["tags"] == ["期末","高数"]
            assert (await client.get('/api/library?offset_minutes=0')).json()["activity"][-1]["date"] == "2026-10-22"
            assert (await client.get('/api/library?offset_minutes=900')).status_code == 422
            assert (await client.put(f'/api/decks/{deck}/tags',json={"tags":["x"*17]})).status_code == 422
            assert (await client.put('/api/decks/999/tags',json={"tags":[]})).status_code == 404


@pytest.mark.parametrize("body",[{"revision":0,"index":-1},{"revision":0,"index":0,"selected_index":4},{"revision":True,"index":0,"selected_index":0}])
async def test_session_rejects_invalid_answers(config,body):
    app=create_app(config)
    async with app.router.lifespan_context(app):
        deck,_,_=seed(app)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            await client.post(f'/api/decks/{deck}/session',json={})
            assert (await client.post(f'/api/decks/{deck}/session/all/answer',json=body)).status_code == 422
