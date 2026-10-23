"""浏览器开发入口；桌面 sidecar 将复用相同工厂和环境配置。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.config import Settings, settings
from app.db import Base, create_database
from app.routers import cards, content, learning, review, settings as settings_router, study, tasks, upload
from app.services.task_manager import TaskManager
from app.services.study_ai import StudyAIManager


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine, sessions = create_database(config)
        Base.metadata.create_all(engine)
        manager = TaskManager(config, sessions)
        manager.recover()
        study_manager = StudyAIManager(config, sessions, manager.generator.semaphore)
        study_manager.recover()
        manager.study_manager = study_manager
        application.state.study_manager = study_manager
        application.state.sessions = sessions
        application.state.config = config
        application.state.task_manager = manager
        try:
            yield
        finally:
            await manager.shutdown()
            await study_manager.shutdown()
            engine.dispose()

    application = FastAPI(title="Zhiye", version="0.5.1", lifespan=lifespan)

    @application.exception_handler(StaleDataError)
    async def stale_progress(_request: Request, _error: StaleDataError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "学习进度已在其他窗口更新，请重新载入"})

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # Pydantic 默认错误响应会回显输入，设置接口可能因此泄露密钥。
        return JSONResponse(status_code=422, content={"detail": "输入格式不正确，请检查字段、文件和选项范围"})
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(upload.router)
    application.include_router(tasks.router)
    application.include_router(cards.router)
    application.include_router(content.router)
    application.include_router(learning.router)
    application.include_router(review.router)
    application.include_router(study.router)
    application.include_router(settings_router.router)
    return application


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
