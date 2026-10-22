"""复习资料和 Word 下载接口。"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response

from app.models import Deck
from app.schemas import StudyMaterial
from app.services.study_material import build_study_docx, build_study_material

router = APIRouter(prefix="/api/decks", tags=["study"])


def load_material(deck_id: int, request: Request) -> StudyMaterial:
    """在短会话内读取知识点，文档构建不占用数据库会话。"""
    with request.app.state.sessions() as session:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise HTTPException(404, "课件不存在")
        material = build_study_material(session, deck)
    if not material.points:
        raise HTTPException(422, "筛选后没有可用知识点，请上传包含知识正文的课件")
    return material


@router.get("/{deck_id}/study", response_model=StudyMaterial)
def study_material(deck_id: int, request: Request) -> StudyMaterial:
    return load_material(deck_id, request)


@router.get("/{deck_id}/study.docx")
def download_word(deck_id: int, request: Request) -> Response:
    material = load_material(deck_id, request)
    filename = quote(material.title[:100] + "-精简复习资料.docx", safe="")
    return Response(build_study_docx(material),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename=zhiye-review.docx; filename*=UTF-8''{filename}"})
