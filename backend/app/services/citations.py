"""提取真实页码并校验引文，不根据知识卡顺序推测来源。"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeckSource, SourcePage
from app.schemas import MapNode, RevisionMap, RevisionNotes, SourceRef
from app.services.parser import TextBlock


def extract_pages(blocks: list[TextBlock]) -> dict[int, str]:
    """按解析器写入的页码标记重组正文，兼容跨块切分的长页。"""
    pages: dict[int, list[str]] = {}
    for block in blocks:
        if block.pages is not None:
            for number, text in block.pages.items():
                pages.setdefault(number, []).append(text)
            continue
        matches = list(re.finditer(r"\[第 (\d+) 页/张\]\n", block.text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(block.text)
            text = block.text[match.end():end].strip()
            if text:
                pages.setdefault(int(match.group(1)), []).append(text)
    return {page: "\n".join(parts) for page, parts in pages.items()}


def load_pages(session: Session, deck_id: int) -> dict[int, str]:
    """旧版若保留带页码的解析正文，也可恢复页码；无原文则不编造来源。"""
    rows = session.scalars(select(SourcePage).where(SourcePage.deck_id == deck_id)).all()
    if rows:
        return {row.page_number: row.text for row in rows}
    source = session.get(DeckSource, deck_id)
    return extract_pages([TextBlock(0, "", source.text)]) if source else {}


def verified_refs(refs: list[SourceRef], pages: dict[int, str]) -> list[SourceRef]:
    """仅保留页码存在且引文确实出现在该页的引用；这不代表结论已被验证。"""
    def normalize(text: str) -> str:
        return re.sub(r"\s+", "", text)
    result: list[SourceRef] = []
    seen: set[tuple[int, str]] = set()
    for ref in refs:
        identity = (ref.page, normalize(ref.quote))
        if identity not in seen and ref.page in pages and identity[1] in normalize(pages[ref.page]):
            result.append(ref)
            seen.add(identity)
    return result


def verify_material_sources(material: RevisionNotes | RevisionMap, pages: dict[int, str]) -> None:
    """在保存提纲或导图前统一校验引用。"""
    def visit(nodes: list[MapNode]) -> None:
        for node in nodes:
            node.source_refs = verified_refs(node.source_refs, pages)
            visit(node.children)
    if isinstance(material, RevisionNotes):
        for section in material.sections:
            section.source_refs = verified_refs(section.source_refs, pages)
    else:
        visit(material.branches)
