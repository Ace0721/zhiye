from pathlib import Path

import pytest

from app.config import Settings
from app.db import Base, create_database
from app.models import AppSetting
from app.services.ai_client import resolve_ai_config


def test_environment_and_database_priority(config: Settings) -> None:
    engine, sessions = create_database(config)
    Base.metadata.create_all(engine)
    with sessions.begin() as session:
        session.add_all([AppSetting(key="model", value="database-model"),
                         AppSetting(key="api_key", value="")])
    with sessions() as session:
        result = resolve_ai_config(session, config)
    assert result.model == "database-model"
    assert result.api_key == ""
    assert result.base_url == config.ai_base_url
    assert config.ai_api_key not in repr(result)
    assert Path(config.data_dir / "zhiye.db").exists()
    engine.dispose()


def test_defaults_and_sidecar_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ZHIYE_PORT", "ZHIYE_DATA_DIR", "ZHIYE_AI_BASE_URL", "ZHIYE_AI_API_KEY",
                 "ZHIYE_AI_MODEL", "ZHIYE_AI_TIMEOUT", "ZHIYE_AI_CONCURRENCY", "ZHIYE_TASK_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.replace("ZHIYE_", "SHUAKE_", 1), raising=False)
    monkeypatch.chdir(tmp_path)
    defaults = Settings()
    assert defaults.port == 8000
    assert defaults.data_dir == tmp_path / "data"
    assert defaults.ai_api_key == ""
    assert (defaults.ai_timeout, defaults.ai_concurrency, defaults.task_timeout) == (60, 3, 600)
    monkeypatch.setenv("ZHIYE_PORT", "43219")
    monkeypatch.setenv("ZHIYE_DATA_DIR", str(tmp_path / "AppData" / "知页"))
    desktop = Settings()
    assert desktop.port == 43219
    assert "知页" in desktop.database_url


@pytest.mark.parametrize("value", ["0", "-1", "abc", "65536"])
def test_invalid_port(config: Settings, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ZHIYE_PORT", value)
    with pytest.raises(ValueError, match="ZHIYE_PORT"):
        Settings()


def test_legacy_environment_and_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlite3
    for name in ("ZHIYE_PORT", "ZHIYE_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SHUAKE_PORT", "43210")
    monkeypatch.setenv("SHUAKE_DATA_DIR", str(tmp_path))
    with sqlite3.connect(tmp_path / "shuake.db") as connection:
        connection.execute("CREATE TABLE rename_check (value TEXT)")
        connection.execute("INSERT INTO rename_check VALUES ('existing-data')")
    legacy = Settings()
    assert legacy.port == 43210
    assert legacy.database_url.endswith("shuake.db")
    monkeypatch.setenv("ZHIYE_PORT", "43211")
    renamed = Settings()
    assert renamed.port == 43211
    engine, _sessions = create_database(renamed)
    with engine.connect() as connection:
        from sqlalchemy import text
        assert connection.execute(text("SELECT value FROM rename_check")).scalar() == "existing-data"
    engine.dispose()
