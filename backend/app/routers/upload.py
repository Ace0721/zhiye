"""接收课件，验证大小，提交本地后台任务。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.schemas import UploadResponse

router = APIRouter(prefix="/api", tags=["upload"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/upload", status_code=202, response_model=UploadResponse)
async def upload(request: Request, file: UploadFile = File(...), outputs: str = Form("cards")) -> UploadResponse:
    """上传完成后即返回 task_id，解析和生成不阻塞响应。"""
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(filename).suffix.lower()
    path: Path | None = None
    submitted = False
    try:
        # 表单空字符串不能被 FastAPI 的默认值误当成“生成卡片”。
        raw_outputs = (await request.form()).get("outputs", outputs)
        if not isinstance(raw_outputs, str):
            raise HTTPException(422, "生成内容格式不正确")
        selected = list(dict.fromkeys(item.strip() for item in raw_outputs.split(",")))
        if not selected or any(item not in {"cards", "notes", "map"} for item in selected):
            raise HTTPException(422, "请至少选择一种生成内容：cards、notes、map，可用逗号分隔")
        if suffix not in {".pdf", ".pptx"}:
            raise HTTPException(415, "仅支持 .pdf 和 .pptx 文件")
        if len(filename) > 255:
            raise HTTPException(400, "文件名过长，请缩短后上传")
        if file.size is not None and file.size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "课件不能超过 50MB")
        manager = request.app.state.task_manager
        path = manager.upload_dir / f"upload-{uuid4()}{suffix}"
        size = 0
        with path.open("xb") as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "课件不能超过 50MB")
                await asyncio.to_thread(stream.write, chunk)
        if size == 0:
            raise HTTPException(400, "课件为空，请选择有效文件")
        task_id = manager.submit(path, filename, selected)
        submitted = True
        return UploadResponse(task_id=task_id)
    except HTTPException:
        raise
    except OSError:
        raise HTTPException(500, "保存课件失败，请检查数据目录权限和磁盘空间") from None
    finally:
        await file.close()
        if path is not None and not submitted:
            path.unlink(missing_ok=True)
