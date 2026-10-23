"""内容编辑、删除、单卡重新生成和本地来源核对。"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AnswerRecord, Card, CardSource, Deck, StudyArtifact
from app.routers.cards import card_response
from app.schemas import CardResponse, GeneratedCard, RevisionMap, RevisionNotes
from app.services.ai_client import AIError, resolve_ai_config
from app.services.card_gen import PROMPT_PATH, parse_cards
from app.services.citations import load_pages, verified_refs, verify_material_sources
from app.services.study_ai import StudyKind

router = APIRouter(prefix="/api", tags=["content"])


class CardEdit(GeneratedCard):
    revision: int = Field(ge=0)


class CardRegenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)


class StudyEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    data: dict


def apply_card_edit(session: Session, card: Card, data: GeneratedCard, revision: int) -> CardResponse:
    """比较版本后保存；题目变化时重置旧答题记录，避免历史错题指向新题。"""
    current_revision = card.provenance.revision if card.provenance else 0
    if current_revision != revision:
        raise HTTPException(409, "这张卡已被修改，请重新载入后再保存")
    options = json.loads(card.options_json)
    if (card.question, options, card.correct_index) != (data.question, data.options, data.correct_index):
        session.execute(delete(AnswerRecord).where(AnswerRecord.card_id == card.id))
    for key, value in data.model_dump(exclude={"options", "source_refs", "revision"}).items():
        setattr(card, key, value)
    card.options_json = json.dumps(data.options, ensure_ascii=False)
    if card.provenance is None:
        card.provenance = CardSource(revision=0)
    refs = verified_refs(data.source_refs, load_pages(session, card.deck_id))
    card.provenance.refs_json = json.dumps([ref.model_dump() for ref in refs], ensure_ascii=False)
    card.provenance.revision = current_revision + 1
    session.flush()
    return card_response(card)


@router.put("/cards/{card_id}", response_model=CardResponse)
def edit_card(card_id: int, body: CardEdit, request: Request) -> CardResponse:
    with request.app.state.sessions.begin() as session:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(404, "卡片不存在")
        return apply_card_edit(session, card, body, body.revision)


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, request: Request) -> Response:
    with request.app.state.sessions.begin() as session:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(404, "卡片不存在")
        session.execute(delete(AnswerRecord).where(AnswerRecord.card_id == card_id))
        session.delete(card)
    return Response(status_code=204)


@router.post("/cards/{card_id}/regenerate", response_model=CardResponse)
async def regenerate_card(card_id: int, body: CardRegenerate, request: Request) -> CardResponse:
    """只重写当前知识点；不持有跨网络事务，不覆盖并发的手动编辑。"""
    manager = request.app.state.task_manager
    config = request.app.state.config
    with request.app.state.sessions() as session:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(404, "卡片不存在")
        snapshot = card_response(card)
        if snapshot.revision != body.revision:
            raise HTTPException(409, "卡片已修改，请重新载入")
        pages = load_pages(session, card.deck_id)
        source = "\n".join(f"[第 {ref.page} 页/张]\n{pages[ref.page]}" for ref in snapshot.source_refs if ref.page in pages)
        ai_config = resolve_ai_config(session, config)
    client = None
    try:
        async with asyncio.timeout(min(config.task_timeout, 2 * config.ai_timeout + 5)):
            client = manager.client_factory(ai_config, config.ai_timeout)
            prompt = PROMPT_PATH.read_text(encoding="utf-8") + "\n本次只重写输入中指定的一张卡，知识点不变，换一种清晰具体的说法。必须返回长度为1的数组。"
            text = "当前知识点：" + snapshot.model_dump_json() + "\n可核对的原文：\n" + source
            for attempt in range(2):
                try:
                    async with manager.generator.semaphore:
                        generated = parse_cards(await client.complete(prompt, text))
                    if len(generated) != 1:
                        raise AIError("单卡生成未返回恰好一张知识卡", retryable=True)
                    generated[0].source_refs = verified_refs(generated[0].source_refs, pages)
                    break
                except AIError as exc:
                    if not exc.retryable or attempt == 1:
                        raise
                    await asyncio.sleep(1)
            with request.app.state.sessions.begin() as session:
                card = session.get(Card, card_id)
                if card is None:
                    raise HTTPException(404, "卡片已删除")
                return apply_card_edit(session, card, generated[0], body.revision)
    except AIError as exc:
        raise HTTPException(400, str(exc)) from None
    except TimeoutError:
        raise HTTPException(504, "单卡重新生成超时，请稍后重试") from None
    finally:
        if client:
            try:
                async with asyncio.timeout(5):
                    await client.close()
            except Exception:
                pass


@router.put("/decks/{deck_id}/study/{kind}")
def edit_study(deck_id: int, kind: StudyKind, body: StudyEdit, request: Request) -> dict:
    model = RevisionNotes if kind == "notes" else RevisionMap
    try:
        material = model.model_validate(body.data)
    except ValidationError:
        message = "提纲至少需要一个有正文的主题，请检查空白字段或异常过大的内容" if kind == "notes" else "导图需要主题与下级概念，最多3层分支、65个节点，节点名至多28字"
        raise HTTPException(422, message) from None
    with request.app.state.sessions.begin() as session:
        row = session.scalar(select(StudyArtifact).where(StudyArtifact.deck_id == deck_id, StudyArtifact.kind == kind))
        if row is None or row.status != "completed":
            raise HTTPException(409, "请先完成生成后再编辑")
        if row.updated_at.isoformat() != body.revision:
            raise HTTPException(409, "内容已更新，请重新载入后再编辑")
        verify_material_sources(material, load_pages(session, deck_id))
        row.content_json = material.model_dump_json()
    return request.app.state.study_manager.snapshot(deck_id, kind)


@router.get("/decks/{deck_id}/sources/{page_number}")
def source_page(deck_id: int, page_number: int, request: Request) -> dict:
    with request.app.state.sessions() as session:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise HTTPException(404, "课件不存在")
        pages = load_pages(session, deck_id)
        if page_number not in pages:
            raise HTTPException(404, "没有保存这一页的解析正文，旧课件可重新上传补齐来源")
        return dict(page=page_number, text=pages[page_number], source_filename=deck.source_filename)
