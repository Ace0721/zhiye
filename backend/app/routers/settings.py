"""设置读取绝不返回密钥，连接测试支持未保存的当前表单。"""

import asyncio

from fastapi import APIRouter, Request

from app.models import AppSetting
from app.schemas import SettingsInput, SettingsResponse
from app.services.ai_client import AIClient, AIConfig, AIError, resolve_ai_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(request: Request) -> SettingsResponse:
    with request.app.state.sessions() as session:
        config = resolve_ai_config(session, request.app.state.config)
    return SettingsResponse(base_url=config.base_url, model=config.model, api_key_configured=bool(config.api_key.strip()))


@router.put("", response_model=SettingsResponse)
def save_settings(body: SettingsInput, request: Request) -> SettingsResponse:
    """空密钥表示不修改，包括首次配置时回退到环境密钥。"""
    values = {"base_url": body.base_url, "model": body.model}
    if body.api_key and body.api_key.strip():
        values["api_key"] = body.api_key.strip()
    with request.app.state.sessions.begin() as session:
        for key, value in values.items():
            record = session.get(AppSetting, key)
            if record is None:
                session.add(AppSetting(key=key, value=value))
            else:
                record.value = value
    return get_settings(request)


@router.post("/test")
async def test_connection(request: Request, body: SettingsInput | None = None) -> dict[str, bool | str | None]:
    """调用一次最小 completion，瞬时故障最多退避重试一次，不保存表单。"""
    manager = request.app.state.task_manager
    with request.app.state.sessions() as session:
        saved = resolve_ai_config(session, request.app.state.config)
    config = AIConfig(body.base_url, (body.api_key or "").strip() or saved.api_key, body.model) if body else saved
    client: AIClient | None = None
    try:
        client = AIClient(config, request.app.state.config.ai_timeout)
        async with asyncio.timeout(request.app.state.config.ai_timeout * 2 + 2):
            for attempt in range(2):
                try:
                    async with manager.generator.semaphore:
                        await client.complete("Reply briefly.", "Hi", max_tokens=1)
                    return {"success": True, "error_type": None, "message": "连接成功，当前配置可以使用"}
                except AIError as exc:
                    if not exc.retryable or attempt == 1:
                        raise
                    await asyncio.sleep(1)
    except TimeoutError:
        return {"success": False, "error_type": "网络超时", "message": "连接测试超时，请等待正在运行的任务结束后重试"}
    except AIError as exc:
        return {"success": False, "error_type": exc.error_type, "message": str(exc)}
    finally:
        if client is not None:
            await client.close()
    return {"success": False, "error_type": "其他", "message": "连接测试未完成"}
