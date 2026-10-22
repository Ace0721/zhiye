"""保存学习现场与首页数据；答题和回炉队列在同一事务提交。"""

import json
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnswerRecord, Card, Deck, DeckLabel, LearningSession, StudyArtifact, utcnow
from app.routers.cards import card_response

router = APIRouter(prefix="/api", tags=["learning"])
Mode = Literal["all", "wrong"]


class OpenSession(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Mode = "all"
    restart: bool = False


class MoveSession(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    index: int = Field(ge=0)
    completed: bool = False


class SessionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    index: int = Field(ge=0)
    selected_index: int = Field(ge=0, le=3)


class TagsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tags: list[str] = Field(max_length=6)


def queue_item(card: Card) -> dict:
    """仅题目指纹变化时清除本轮答案，文字润色不打断学习。"""
    signature = sha256(json.dumps([card.question, card.options_json, card.correct_index]).encode()).hexdigest()
    return dict(id=card.id, revision=card.provenance.revision if card.provenance else 0, signature=signature)


def session_state(session: Session, row: LearningSession) -> tuple[dict, dict[int, Card]]:
    """修复删除或修改的卡片，不把旧答案套到新题上。"""
    state = json.loads(row.state_json)
    cards = {card.id: card for card in session.scalars(select(Card).where(Card.deck_id == row.deck_id))}
    old_queue = state["queue"]
    retained = [(position, item) for position, item in enumerate(old_queue) if item["id"] in cards]
    queue = []
    invalidated = False
    for _, item in retained:
        card = cards[item["id"]]
        fresh = queue_item(card)
        if item.get("signature") != fresh["signature"]:
            item = fresh
            invalidated = True
        else:
            item = {**item, **fresh}
        queue.append(item)
    index = min(sum(position < state["index"] for position, _ in retained), max(0, len(queue) - 1))
    if queue != old_queue or index != state["index"]:
        state.update(queue=queue, index=index, initial_count=min(state["initial_count"], len({item["id"] for item in queue})))
        if invalidated:
            state["completed"] = False
            state["index"] = next((i for i, item in enumerate(queue) if "selected" not in item), index)
        row.state_json = json.dumps(state)
        row.revision += 1
        session.flush()
    return state, cards


def snapshot(session: Session, row: LearningSession) -> dict:
    state, cards = session_state(session, row)
    answers = {}
    for index, item in enumerate(state["queue"]):
        if "selected" in item:
            card = cards[item["id"]]
            answers[index] = dict(selected_index=item["selected"], is_correct=item["selected"] == card.correct_index, reexplain=card.reexplain)
    return dict(queue=[card_response(cards[item["id"]]) for item in state["queue"]], answers=answers,
                index=state["index"], initial_count=state["initial_count"], completed=state["completed"],
                revision=row.revision, mode=row.mode, updated_at=row.updated_at.replace(tzinfo=timezone.utc))


def current_session(session: Session, deck_id: int, mode: Mode, revision: int) -> tuple[LearningSession, dict, dict[int, Card]]:
    row = session.get(LearningSession, (deck_id, mode))
    if row is None:
        raise HTTPException(409, "学习现场不存在，请重新载入")
    state, cards = session_state(session, row)
    if row.revision != revision:
        raise HTTPException(409, "学习进度或卡片已更新，请点击重新载入")
    return row, state, cards


@router.post("/decks/{deck_id}/session")
def open_session(deck_id: int, body: OpenSession, request: Request) -> dict:
    """默认恢复；只有明确重新学习才替换本轮进度，保留历史答题。"""
    with request.app.state.sessions.begin() as session:
        if session.get(Deck, deck_id) is None:
            raise HTTPException(404, "课件不存在")
        row = session.get(LearningSession, (deck_id, body.mode))
        if row is None or body.restart or not json.loads(row.state_json)["queue"]:
            query = select(Card).where(Card.deck_id == deck_id).order_by(Card.order_index)
            if body.mode == "wrong":
                query = query.where(select(AnswerRecord.id).where(AnswerRecord.card_id == Card.id, AnswerRecord.is_correct.is_(False)).exists())
            cards = session.scalars(query).all()
            state = dict(queue=[queue_item(card) for card in cards],
                         index=0, initial_count=len(cards), completed=False)
            if row is None:
                row = LearningSession(deck_id=deck_id, mode=body.mode, state_json=json.dumps(state))
                session.add(row)
            else:
                row.state_json = json.dumps(state)
                row.revision += 1
            session.flush()
        return snapshot(session, row)


@router.put("/decks/{deck_id}/session/{mode}")
def move_session(deck_id: int, mode: Mode, body: MoveSession, request: Request) -> dict:
    with request.app.state.sessions.begin() as session:
        row, state, _ = current_session(session, deck_id, mode, body.revision)
        queue = state["queue"]
        if not queue or body.index >= len(queue):
            raise HTTPException(422, "卡片位置无效，请重新载入")
        if body.index > state["index"] and any("selected" not in item for item in queue[state["index"]:body.index]):
            raise HTTPException(422, "请先回答当前题目")
        if body.completed and any("selected" not in item for item in queue):
            raise HTTPException(422, "还有未完成的题目")
        state.update(index=body.index, completed=body.completed)
        row.state_json = json.dumps(state)
        row.revision += 1
        session.flush()
        return snapshot(session, row)


@router.post("/decks/{deck_id}/session/{mode}/answer")
def answer_session(deck_id: int, mode: Mode, body: SessionAnswer, request: Request) -> dict:
    """答题、追加错题和现场版本一起提交，断线重试不会重复计数。"""
    with request.app.state.sessions.begin() as session:
        row, state, cards = current_session(session, deck_id, mode, body.revision)
        if body.index != state["index"] or body.index >= len(state["queue"]) or state["completed"]:
            raise HTTPException(409, "当前位置已变化，请重新载入")
        item = state["queue"][body.index]
        if "selected" in item:
            raise HTTPException(409, "这道题已提交，请重新载入")
        card = cards[item["id"]]
        correct = body.selected_index == card.correct_index
        session.add(AnswerRecord(card_id=card.id, selected_index=body.selected_index, is_correct=correct))
        item["selected"] = body.selected_index
        if not correct:
            state["queue"].append(queue_item(card))
        row.state_json = json.dumps(state)
        row.revision += 1
        session.flush()
        return snapshot(session, row)


@router.put("/decks/{deck_id}/tags")
def save_tags(deck_id: int, body: TagsInput, request: Request) -> dict:
    tags = list(dict.fromkeys(tag.strip() for tag in body.tags if tag.strip()))
    if any(len(tag) > 16 for tag in tags):
        raise HTTPException(422, "每个标签最多16字")
    with request.app.state.sessions.begin() as session:
        if session.get(Deck, deck_id) is None:
            raise HTTPException(404, "课件不存在")
        row = session.get(DeckLabel, deck_id)
        if row is None:
            session.add(DeckLabel(deck_id=deck_id, tags_json=json.dumps(tags, ensure_ascii=False)))
        else:
            row.tags_json = json.dumps(tags, ensure_ascii=False)
    return {"tags": tags}


@router.get("/library")
def library(request: Request, offset_minutes: int = Query(default=0, ge=-840, le=840)) -> dict:
    """按浏览器时区统计真实答题；同卡重复回炉只算一个学习知识点。"""
    zone = timezone(timedelta(minutes=offset_minutes))
    today = utcnow().astimezone(zone).date()
    first = today - timedelta(days=6)
    start = datetime.combine(first, datetime.min.time(), zone).astimezone(timezone.utc)
    with request.app.state.sessions.begin() as session:
        decks = session.scalars(select(Deck).order_by(Deck.created_at.desc(), Deck.id.desc())).all()
        counts = dict(session.execute(select(Card.deck_id, func.count(Card.id)).group_by(Card.deck_id)).all())
        learned = dict(session.execute(select(Card.deck_id, func.count(func.distinct(Card.id))).join(AnswerRecord).group_by(Card.deck_id)).all())
        wrong = dict(session.execute(select(Card.deck_id, func.count(func.distinct(Card.id))).join(AnswerRecord).where(AnswerRecord.is_correct.is_(False)).group_by(Card.deck_id)).all())
        latest = dict(session.execute(select(Card.deck_id, func.max(AnswerRecord.created_at)).join(AnswerRecord).group_by(Card.deck_id)).all())
        ready: dict[int, list[str]] = {}
        for deck_id, kind in session.execute(select(StudyArtifact.deck_id, StudyArtifact.kind).where(StudyArtifact.status == "completed")):
            ready.setdefault(deck_id, []).append(kind)
        labels = {row.deck_id: json.loads(row.tags_json) for row in session.scalars(select(DeckLabel))}
        activity: dict[str, set[int]] = {(first + timedelta(days=i)).isoformat(): set() for i in range(7)}
        for card_id, at in session.execute(select(AnswerRecord.card_id, AnswerRecord.created_at).where(AnswerRecord.created_at >= start)):
            day = at.replace(tzinfo=timezone.utc).astimezone(zone).date().isoformat()
            if day in activity:
                activity[day].add(card_id)
        sessions = { (row.deck_id, row.mode): row for row in session.scalars(select(LearningSession)) }
        result = []
        resumes = []
        for deck in decks:
            saved = []
            for mode in ("all", "wrong"):
                row = sessions.get((deck.id, mode))
                if row:
                    state, _ = session_state(session, row)
                    if state["queue"]:
                        item = dict(deck_id=deck.id, title=deck.title, mode=mode, index=state["index"], total=len(state["queue"]),
                                    answered=sum("selected" in item for item in state["queue"]), completed=state["completed"], updated_at=row.updated_at)
                        saved.append(item)
                        if not item["completed"]:
                            resumes.append(item)
            result.append(dict(id=deck.id, title=deck.title, source_filename=deck.source_filename, created_at=deck.created_at,
                               card_count=counts.get(deck.id, 0), learned_count=learned.get(deck.id, 0), wrong_count=wrong.get(deck.id, 0),
                               last_studied_at=latest.get(deck.id), tags=labels.get(deck.id, []), sessions=saved,
                               available_outputs=(["cards"] if counts.get(deck.id) else []) + ready.get(deck.id, [])))
        resumes.sort(key=lambda row: row["updated_at"].replace(tzinfo=timezone.utc).timestamp(), reverse=True)
        return dict(decks=result, resume=resumes[0] if resumes else None,
                    stats=dict(deck_count=len(decks), card_count=sum(counts.values()), learned_count=sum(learned.values()),
                               wrong_count=sum(wrong.values()), today_count=len(activity[today.isoformat()])),
                    activity=[dict(date=day, count=len(ids)) for day, ids in activity.items()])
