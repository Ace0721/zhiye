"""按历史错题汇总复习内容并导出 Word，不再请求 AI。"""

import json
from io import BytesIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnswerRecord, Card, Deck
from app.schemas import ReviewSummary, SummaryPoint, SummaryQuestion
from app.services.study_material import create_word_document, document_text


def build_summary(session: Session, deck: Deck) -> ReviewSummary:
    """错题按错误次数降序排列；零错题时保留全课重点速记。"""
    cards = session.scalars(select(Card).where(Card.deck_id == deck.id).order_by(Card.order_index)).all()
    counts = dict(session.execute(select(AnswerRecord.card_id, func.count(AnswerRecord.id))
                                 .join(Card).where(Card.deck_id == deck.id, AnswerRecord.is_correct.is_(False))
                                 .group_by(AnswerRecord.card_id)).all())
    wrong = sorted((card for card in cards if card.id in counts), key=lambda card: (-counts[card.id], card.order_index))
    return ReviewSummary(title=deck.title, total_cards=len(cards), wrong_count=len(wrong),
        points=[SummaryPoint(card_id=card.id, title=card.title, key_point=card.key_point,
                             wrong_count=counts.get(card.id, 0), source_refs=json.loads(card.provenance.refs_json) if card.provenance else []) for card in wrong or cards],
        wrong_cards=[SummaryQuestion(card_id=card.id, title=card.title, question=card.question,
                     correct_answer=f"{'ABCD'[card.correct_index]}. {json.loads(card.options_json)[card.correct_index]}",
                     reexplain=card.reexplain, wrong_count=counts[card.id], source_refs=json.loads(card.provenance.refs_json) if card.provenance else []) for card in wrong])


def build_summary_docx(summary: ReviewSummary) -> bytes:
    """把页面相同的薄弱点、错题答案与补充解释排版成可编辑 Word。"""
    document = create_word_document(summary.title + " 考前救命包", "知页 Zhiye  根据本地答题记录整理")
    document.add_paragraph(f"知识卡 {summary.total_cards} 张，历史错题 {summary.wrong_count} 张。"
                           "先复习高频薄弱点，再回看错题解释；请结合原课件核对 AI 内容。")
    document.add_heading("高频易错重点" if summary.wrong_count else "重点速记", level=1)
    for point in summary.points:
        paragraph = document.add_paragraph()
        paragraph.add_run(document_text(point.title)).bold = True
        frequency = f"（答错 {point.wrong_count} 次）" if point.wrong_count else ""
        paragraph.add_run(f"{frequency}：{document_text(point.key_point)}")
        if point.source_refs:
            document.add_paragraph("参考来源：" + "、".join(f"第 {page} 页/张" for page in dict.fromkeys(ref.page for ref in point.source_refs)))
    document.add_heading("错题回顾", level=1)
    for index, card in enumerate(summary.wrong_cards, 1):
        document.add_heading(f"{index} {document_text(card.title)}", level=2)
        document.add_paragraph("题目：" + document_text(card.question))
        document.add_paragraph("正确答案：" + document_text(card.correct_answer))
        document.add_paragraph("再讲一遍：" + document_text(card.reexplain))
    if not summary.wrong_cards:
        document.add_paragraph("暂无历史错题，可以先复习上方重点，再通过刷卡自测检验掌握情况。")
    output = BytesIO()
    document.save(output)
    return output.getvalue()
