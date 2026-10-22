import json

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.models import Card, Deck
from app.schemas import CardResponse, DeckResponse

router = APIRouter(prefix="/api/decks", tags=["cards"])


def card_response(card: Card) -> CardResponse:
    return CardResponse(
        id=card.id, deck_id=card.deck_id, order_index=card.order_index,
        title=card.title, plain_explanation=card.plain_explanation, key_point=card.key_point,
        question=card.question, options=json.loads(card.options_json), correct_index=card.correct_index,
        reexplain=card.reexplain, created_at=card.created_at,
    )


@router.get("", response_model=list[DeckResponse])
def get_decks(request: Request) -> list[DeckResponse]:
    """返回本机已生成的课件，刷新页面后仍可继续学习。"""
    with request.app.state.sessions() as session:
        rows = session.execute(select(Deck, func.count(Card.id)).outerjoin(Card).group_by(Deck.id)
                               .order_by(Deck.created_at.desc(), Deck.id.desc())).all()
        return [DeckResponse(id=deck.id, title=deck.title, created_at=deck.created_at, card_count=count)
                for deck, count in rows]


@router.get("/{deck_id}/cards", response_model=list[CardResponse])
def get_cards(deck_id: int, request: Request) -> list[CardResponse]:
    """按课件原始顺序返回卡片，options_json 转换为前端数组。"""
    with request.app.state.sessions() as session:
        if session.get(Deck, deck_id) is None:
            raise HTTPException(404, "卡组不存在")
        cards = session.scalars(select(Card).where(Card.deck_id == deck_id).order_by(Card.order_index)).all()
        return [card_response(card) for card in cards]
