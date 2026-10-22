import json
from pathlib import Path

import pytest

from app.config import Settings


def card_json(title: str = "测试知识点") -> str:
    return json.dumps([{
        "title": title, "plain_explanation": "先理解概念。再结合例子记忆。",
        "key_point": "记住这个知识点", "question": "哪个选项正确？",
        "options": ["正确说法", "常见误解一", "常见误解二", "常见误解三"],
        "correct_index": 0, "reexplain": "换个角度，用具体例子理解。",
    }], ensure_ascii=False)


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ZHIYE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ZHIYE_AI_API_KEY", "test-placeholder")
    monkeypatch.setenv("ZHIYE_AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("ZHIYE_AI_MODEL", "mock-model")
    monkeypatch.setenv("ZHIYE_AI_TIMEOUT", "1")
    monkeypatch.setenv("ZHIYE_AI_CONCURRENCY", "3")
    monkeypatch.setenv("ZHIYE_TASK_TIMEOUT", "10")
    return Settings()
