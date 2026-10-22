"""AI 输出与 HTTP 响应的结构约束。"""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class GeneratedCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: Annotated[NonEmpty, Field(max_length=16)]
    plain_explanation: NonEmpty
    key_point: Annotated[NonEmpty, Field(max_length=40)]
    question: Annotated[NonEmpty, Field(max_length=60)]
    options: Annotated[list[NonEmpty], Field(min_length=4, max_length=4)]
    correct_index: Annotated[int, Field(ge=0, le=3)]
    reexplain: NonEmpty

    @field_validator("options")
    @classmethod
    def unique_options(cls, value: list[str]) -> list[str]:
        if len(set(value)) != 4:
            raise ValueError("选项不能重复")
        return value


class CardResponse(GeneratedCard):
    id: int
    deck_id: int
    order_index: int
    created_at: datetime


class FailedBlock(BaseModel):
    block_index: int
    source: str
    error: str


class TaskResponse(BaseModel):
    status: Literal["queued", "parsing", "generating", "completed", "failed"]
    progress: int
    total_blocks: int
    done_blocks: int
    error: str | None
    deck_id: int | None
    card_count: int
    failed_blocks: list[FailedBlock]


class UploadResponse(BaseModel):
    task_id: str


class AnswerInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    selected_index: Annotated[int, Field(ge=0, le=3)]


class AnswerResponse(BaseModel):
    selected_index: int
    is_correct: bool
    reexplain: str


class DeckResponse(BaseModel):
    id: int
    title: str
    card_count: int
    created_at: datetime


class StudyPoint(BaseModel):
    card_id: int
    title: str
    key_point: str
    explanation: str
    clarification: str
    wrong_count: int


class StudyMaterial(BaseModel):
    deck_id: int
    title: str
    points: list[StudyPoint]
    excluded_count: int


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: Annotated[NonEmpty, Field(max_length=2048)]
    model: Annotated[NonEmpty, Field(max_length=255)]
    api_key: Annotated[str, Field(max_length=4096, repr=False)] | None = None

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError
            _ = parts.port
        except ValueError:
            raise ValueError("请输入有效的 HTTP(S) base_url，不要在 URL 中放入密钥、查询参数或账号") from None
        return value.rstrip("/")


class SettingsResponse(BaseModel):
    base_url: str
    model: str
    api_key_configured: bool
