"""用已提炼的课件知识生成复习资料，导出不再调用云端 AI。"""

import re
from io import BytesIO

from docx import Document
from docx.document import Document as WordDocument
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnswerRecord, Card, Deck
from app.schemas import RevisionNotes, StudyMaterial, StudyPoint
from app.services.card_gen import is_course_admin_card


def build_study_material(session: Session, deck: Deck) -> StudyMaterial:
    """保持课件顺序，过滤课程事务与完全重复重点，并附上真实错题次数。"""
    cards = session.scalars(select(Card).where(Card.deck_id == deck.id).order_by(Card.order_index)).all()
    counts = dict(session.execute(select(AnswerRecord.card_id, func.count(AnswerRecord.id))
                                 .join(Card).where(Card.deck_id == deck.id, AnswerRecord.is_correct.is_(False))
                                 .group_by(AnswerRecord.card_id)).all())
    seen: set[str] = set()
    points: list[StudyPoint] = []
    for card in cards:
        identity = re.sub(r"\W+", "", card.key_point).casefold()
        if is_course_admin_card(card) or identity in seen:
            continue
        seen.add(identity)
        points.append(StudyPoint(card_id=card.id, title=card.title, key_point=card.key_point,
                                 explanation=card.plain_explanation, clarification=card.reexplain,
                                 wrong_count=counts.get(card.id, 0)))
    return StudyMaterial(deck_id=deck.id, title=deck.title, points=points,
                         excluded_count=len(cards) - len(points))


def document_text(text: str) -> str:
    """移除 XML 不允许的控制字符，避免异常课件导致 Word 导出失败。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "", text)


def create_word_document(title: str, footer: str) -> WordDocument:
    """复习提纲与错题包使用一致的中文字体、页边距和标题样式。"""
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(0.75)
    section.left_margin = section.right_margin = Inches(0.85)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = document.styles[name]
        style.font.name = "Microsoft YaHei"
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.color.rgb = RGBColor(0, 0, 0)
    normal = document.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing = 1.2
    normal.paragraph_format.space_after = Pt(6)
    document.styles["Title"].font.size = Pt(22)
    document.styles["Heading 1"].font.size = Pt(15)
    document.styles["Heading 2"].font.size = Pt(12)
    document.add_paragraph(document_text(title), "Title")
    section.footer.paragraphs[0].text = document_text(footer)
    return document


def build_study_docx(material: RevisionNotes) -> bytes:
    """仅排版已由 AI 压缩的提纲，不能再次拼接知识卡或重复正文。"""
    document = create_word_document(material.title + " 精简复习资料", "知页 Zhiye  课件复习资料")
    document.add_paragraph(document_text(material.overview))
    for group in material.sections:
        document.add_heading(document_text(group.heading), level=1)
        if group.source_refs:
            document.add_paragraph("参考来源：" + "、".join(f"第 {page} 页/张" for page in dict.fromkeys(ref.page for ref in group.source_refs)))
        for bullet in group.bullets:
            document.add_paragraph(document_text(bullet), style="List Bullet")
    if material.pitfalls:
        document.add_heading("易混与边界", level=1)
        for item in material.pitfalls:
            document.add_paragraph(document_text(item), style="List Bullet")
    output = BytesIO()
    document.save(output)
    return output.getvalue()
