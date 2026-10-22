"""统一读取浏览器开发和桌面 sidecar 的环境配置。"""

import os
from pathlib import Path


def env_value(name: str, default: str) -> str:
    """新配置优先，同时兼容改名前的 SHUAKE 环境变量。"""
    legacy_name = name.replace("ZHIYE_", "SHUAKE_", 1)
    return os.getenv(name, os.getenv(legacy_name, default))


def positive_int(name: str, default: str, maximum: int | None = None) -> int:
    """尽早拒绝无效配置，错误信息不包含敏感环境变量。"""
    try:
        value = int(env_value(name, default))
    except ValueError:
        raise ValueError(f"{name} 必须是正整数") from None
    if value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} 超出允许范围")
    return value


class Settings:
    def __init__(self) -> None:
        self.port = positive_int("ZHIYE_PORT", "8000", 65535)
        self.host = env_value("ZHIYE_HOST", "127.0.0.1")
        self.data_dir = Path(env_value("ZHIYE_DATA_DIR", "./data")).resolve()
        database_path = self.data_dir / "zhiye.db"
        # 已有本地数据继续原地使用，避免改名后看起来像丢失了课件。
        legacy_path = self.data_dir / "shuake.db"
        if not database_path.exists() and legacy_path.exists():
            database_path = legacy_path
        self.database_url = f"sqlite:///{database_path.as_posix()}"
        self.ai_base_url = env_value("ZHIYE_AI_BASE_URL", "https://api.deepseek.com/v1")
        self.ai_api_key = env_value("ZHIYE_AI_API_KEY", "")
        self.ai_model = env_value("ZHIYE_AI_MODEL", "deepseek-chat")
        self.ai_timeout = positive_int("ZHIYE_AI_TIMEOUT", "60")
        self.ai_concurrency = positive_int("ZHIYE_AI_CONCURRENCY", "3")
        self.task_timeout = positive_int("ZHIYE_TASK_TIMEOUT", "600")
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
