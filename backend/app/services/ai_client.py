"""只使用 OpenAI 兼容云端 API，禁止把 SDK 原始异常暴露给用户。"""

import asyncio
from dataclasses import dataclass, field

import openai
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AppSetting


class AIError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, degrade: bool = False, error_type: str = "其他") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.degrade = degrade
        self.error_type = error_type


@dataclass(frozen=True)
class AIConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str = "deepseek-chat"


def resolve_ai_config(session: Session, config: Settings) -> AIConfig:
    """数据库记录存在即覆盖环境配置，包括空值。"""
    def value(key: str, fallback: str) -> str:
        record = session.get(AppSetting, key)
        return record.value if record is not None else fallback

    return AIConfig(
        base_url=value("base_url", config.ai_base_url),
        api_key=value("api_key", config.ai_api_key),
        model=value("model", config.ai_model),
    )


class AIClient:
    def __init__(self, config: AIConfig, timeout: int) -> None:
        if not config.api_key.strip():
            raise AIError("未配置 API Key，请先在 AI 设置页填写，或设置 ZHIYE_AI_API_KEY", error_type="认证失败")
        if not config.model.strip():
            raise AIError("未配置模型名称，请检查 AI 配置")
        try:
            self.client = AsyncOpenAI(base_url=config.base_url, api_key=config.api_key,
                                      timeout=timeout, max_retries=0)
        except Exception:
            raise AIError("AI 配置无效，请检查 base_url 和 API Key") from None
        self.model = config.model
        self.timeout = timeout

    async def complete(self, prompt: str, text: str, *, max_tokens: int | None = None) -> str:
        """单次调用有总时限；重试由拆卡服务统一执行。"""
        try:
            async with asyncio.timeout(self.timeout):
                extra = {"max_tokens": max_tokens} if max_tokens is not None else {}
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                    **extra,
                )
            if response.choices and response.choices[0].finish_reason == "length":
                raise AIError("AI 输出达到长度上限，结果被截断；请压缩文字与来源引文后重试", retryable=True)
            content = response.choices[0].message.content if response.choices else None
            if max_tokens is None and (not isinstance(content, str) or not content.strip()):
                raise AIError("AI 返回了空内容", retryable=True)
            return content or ""
        except AIError:
            raise
        except (TimeoutError, openai.APITimeoutError):
            raise AIError("AI 请求超时，请检查网络或调大 ZHIYE_AI_TIMEOUT", retryable=True, error_type="网络超时") from None
        except openai.APIConnectionError:
            raise AIError("无法连接 AI 服务，请检查网络和 base_url", retryable=True) from None
        except openai.APIStatusError as exc:
            status = exc.status_code
            body = exc.body if isinstance(exc.body, dict) else {}
            detail = body.get("error", body)
            code = str(detail.get("code", "")).lower() if isinstance(detail, dict) else ""
            missing_model = status == 404 or code in {"model_not_found", "model_not_exist", "invalid_model", "invalid_model_name"}
            if status in (401, 403):
                message = "AI 认证失败或无访问权限，请检查 API Key"
            elif missing_model:
                message = "AI 模型或接口不存在，请检查 model 和 base_url"
            elif status == 429:
                message = "AI 服务限流或额度不足（429），请稍后重试或检查账户额度"
            elif status >= 500:
                message = "AI 服务暂时不可用（5xx），请稍后重试"
            else:
                message = f"AI 服务拒绝请求（HTTP {status}），请检查配置和请求限制"
            transient = status == 429 or status >= 500
            category = "认证失败" if status in (401, 403) else "模型不存在" if missing_model else "其他"
            raise AIError(message, retryable=transient, degrade=transient, error_type=category) from None
        except Exception:
            raise AIError("AI 请求失败，请检查服务配置或稍后重试") from None

    async def close(self) -> None:
        await self.client.close()
