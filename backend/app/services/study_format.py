"""将模型的普通提纲整理为统一结构，不因排版细节丢弃整份正文。"""

import re

from pydantic import ValidationError

from app.schemas import SourceRef


def clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"(?<![A-Za-z0-9_*])\*\*(.+?)\*\*(?![A-Za-z0-9_*])", r"\1", value.strip())
    return re.sub(r"`([^`\n]+)`", r"\1", value).strip()


def text_items(value: object) -> list[str]:
    """兼容单字符串和字符串列表，去掉空行及完全重复的要点。"""
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(text for item in value if (text := clean_text(item))))


def optional_refs(value: object) -> list[dict]:
    """来源是辅助信息，缺失或格式异常不阻止生成正文。"""
    refs = []
    if isinstance(value, list):
        for item in value[:6]:
            try:
                refs.append(SourceRef.model_validate(item).model_dump())
            except ValidationError:
                continue
    return refs


def normalize_notes(value: object) -> dict | None:
    """兼容旧JSON结果，忽略额外字段，不凭空补写知识结论。"""
    if not isinstance(value, dict):
        return None
    for wrapper in ("notes", "data"):
        if isinstance(value.get(wrapper), dict) and "sections" not in value:
            value = value[wrapper]
    sections = []
    raw = value.get("sections", [])
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            bullets = text_items(item.get("bullets", item.get("points", item.get("content", []))))
            if bullets:
                sections.append(dict(heading=clean_text(item.get("heading", item.get("title"))) or "重点速记",
                                     bullets=bullets, source_refs=optional_refs(item.get("source_refs"))))
    if not sections:
        return None
    return dict(title=clean_text(value.get("title")) or "课程复习提纲", overview=clean_text(value.get("overview", value.get("summary"))),
                sections=sections, pitfalls=text_items(value.get("pitfalls")))


def markdown_notes(content: str) -> dict | None:
    """按标题与段落整理Markdown；公式、条件和句子完整保留，不机械截字。"""
    title, overview, sections, pitfalls = "课程复习提纲", [], [], []
    section: dict | None = None
    in_pitfalls = False
    structured = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("```"):
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            structured = True
            name = clean_text(heading[2])
            if len(heading[1]) == 1 and not sections and not overview and title == "课程复习提纲":
                title = name
                continue
            in_pitfalls = name.rstrip("：:") in {"易混点", "易混与边界", "易错点", "注意事项", "易混区别"}
            if not in_pitfalls:
                section = dict(heading=name, bullets=[], source_refs=[])
                sections.append(section)
            continue
        citation = re.match(r"^>\s*来源[：:]\s*第?\s*(\d+)\s*(?:页/张|页|张)\s*[|｜]\s*(.+)$", line)
        if citation:
            if section and not in_pitfalls and len(section["source_refs"]) < 6:
                section["source_refs"].extend(optional_refs([dict(page=int(citation[1]),quote=citation[2].strip())]))
            continue
        bullet = re.match(r"^(?:[-*+]\s+|\d+[.、)）]\s*)(.+)$", line)
        structured = structured or bool(bullet)
        text = clean_text(bullet[1] if bullet else line)
        if not text:
            continue
        if in_pitfalls:
            pitfalls.append(text)
        elif section is not None:
            section["bullets"].append(text)
        elif bullet:
            section = dict(heading="重点速记", bullets=[text], source_refs=[])
            sections.append(section)
        else:
            overview.append(text)
    sections = [dict(item, bullets=list(dict.fromkeys(item["bullets"]))) for item in sections if item["bullets"]]
    if not sections and overview and (structured or len("".join(overview)) >= 60):
        sections = [dict(heading="重点速记",bullets=overview,source_refs=[])]
        overview = []
    if not sections:
        return None
    return dict(title=title, overview="\n".join(overview), sections=sections, pitfalls=list(dict.fromkeys(pitfalls)))
