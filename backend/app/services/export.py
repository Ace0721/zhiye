"""按历史答错次数汇总 Markdown，不再请求 AI。"""

import json
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnswerRecord, Card, Deck


def markdown_text(value: str) -> str:
    """将课件文本作为文字写入 Markdown，避免意外生成 HTML 或链接。"""
    return re.sub(r"([\\`*_{}\[\]()<>#!|])", r"\\\1", " ".join(value.split()))


def build_summary(session: Session, deck: Deck) -> dict[str, str | int]:
    """错题优先，零错题时提供全部知识卡的重点清单。"""
    cards = session.scalars(select(Card).where(Card.deck_id == deck.id).order_by(Card.order_index)).all()
    counts = dict(session.execute(select(AnswerRecord.card_id, func.count(AnswerRecord.id))
                                 .join(Card).where(Card.deck_id == deck.id, AnswerRecord.is_correct.is_(False))
                                 .group_by(AnswerRecord.card_id)).all())
    wrong = sorted((card for card in cards if card.id in counts), key=lambda card: (-counts[card.id], card.order_index))
    lines = [f"# {markdown_text(deck.title)} · 考前救命包", "", f"知识卡：{len(cards)} 张｜历史错题：{len(wrong)} 张", "",
             "## 高频易错重点" if wrong else "## 重点速记", ""]
    for card in wrong or cards:
        frequency = f"（答错 {counts[card.id]} 次）" if card.id in counts else ""
        lines.append(f"- **{markdown_text(card.title)}**{frequency}：{markdown_text(card.key_point)}")
    lines.extend(["", "## 错题卡片", ""])
    if wrong:
        for card in wrong:
            lines.extend([f"### {markdown_text(card.title)}", "", f"- 题目：{markdown_text(card.question)}",
                          f"- 正确答案：{'ABCD'[card.correct_index]}. {markdown_text(json.loads(card.options_json)[card.correct_index])}",
                          f"- 再讲一遍：{markdown_text(card.reexplain)}", ""])
    else:
        lines.append("暂无历史错题。继续保持，也可以再刷一遍巩固。")
    lines.extend(["", "---", "由 Zhiye 在本地生成。AI 内容可能有误，请结合原课件复习。", ""])
    return {"title": deck.title, "markdown": "\n".join(lines), "wrong_count": len(wrong), "total_cards": len(cards)}
