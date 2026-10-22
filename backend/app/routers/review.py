"""保存真实答题结果，查询历史错题并生成考前救命包。"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app.models import AnswerRecord, Card, Deck
from app.routers.cards import card_response
from app.schemas import AnswerInput, AnswerResponse, CardResponse, ReviewSummary
from app.services.export import build_summary, build_summary_docx

router = APIRouter(prefix="/api", tags=["review"])


@router.post("/cards/{card_id}/answer", response_model=AnswerResponse)
def answer_card(card_id: int, body: AnswerInput, request: Request) -> AnswerResponse:
    """服务端判题并提交记录；前端只在提交成功后确认答案。"""
    with request.app.state.sessions.begin() as session:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(404, "卡片不存在")
        correct = body.selected_index == card.correct_index
        session.add(AnswerRecord(card_id=card_id, selected_index=body.selected_index, is_correct=correct))
        return AnswerResponse(selected_index=body.selected_index, is_correct=correct, reexplain=card.reexplain)


@router.get("/decks/{deck_id}/wrong", response_model=list[CardResponse])
def wrong_cards(deck_id: int, request: Request) -> list[CardResponse]:
    with request.app.state.sessions() as session:
        if session.get(Deck, deck_id) is None:
            raise HTTPException(404, "卡组不存在")
        wrong = select(AnswerRecord.id).where(AnswerRecord.card_id == Card.id, AnswerRecord.is_correct.is_(False)).exists()
        cards = session.scalars(select(Card).where(Card.deck_id == deck_id, wrong).order_by(Card.order_index)).all()
        return [card_response(card) for card in cards]


@router.get("/decks/{deck_id}/summary", response_model=ReviewSummary)
def summary(deck_id: int, request: Request) -> ReviewSummary:
    with request.app.state.sessions() as session:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise HTTPException(404, "卡组不存在")
        return build_summary(session, deck)


@router.get("/decks/{deck_id}/summary.docx")
def download_summary(deck_id: int, request: Request) -> Response:
    material = summary(deck_id, request)
    filename = quote(material.title[:100] + "-考前救命包.docx", safe="")
    return Response(build_summary_docx(material),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename=zhiye-summary.docx; filename*=UTF-8''{filename}"})
