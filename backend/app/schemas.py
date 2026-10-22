"""AI 输出与 HTTP 响应的结构约束。"""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page: Annotated[int, Field(ge=1)]
    quote: Annotated[NonEmpty, Field(max_length=180)]


class GeneratedCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: Annotated[NonEmpty, Field(max_length=16)]
    plain_explanation: NonEmpty
    key_point: Annotated[NonEmpty, Field(max_length=40)]
    question: Annotated[NonEmpty, Field(max_length=60)]
    options: Annotated[list[NonEmpty], Field(min_length=4, max_length=4)]
    correct_index: Annotated[int, Field(ge=0, le=3)]
    reexplain: NonEmpty
    source_refs: Annotated[list[SourceRef], Field(max_length=6)] = Field(default_factory=list)

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
    revision: int = 0


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
    requested_outputs: list[str] = Field(default_factory=lambda: ["cards"])
    generated_outputs: list[str] = Field(default_factory=list)
    output_errors: dict[str, str] = Field(default_factory=dict)


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
    available_outputs: list[str] = Field(default_factory=list)


class SummaryPoint(BaseModel):
    card_id: int
    title: str
    key_point: str
    wrong_count: int
    source_refs: list[SourceRef] = Field(default_factory=list)


class SummaryQuestion(BaseModel):
    card_id: int
    title: str
    question: str
    correct_answer: str
    reexplain: str
    wrong_count: int
    source_refs: list[SourceRef] = Field(default_factory=list)


class ReviewSummary(BaseModel):
    title: str
    total_cards: int
    wrong_count: int
    points: list[SummaryPoint]
    wrong_cards: list[SummaryQuestion]


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


class NotesSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: Annotated[NonEmpty, Field(max_length=24)]
    bullets: Annotated[list[Annotated[NonEmpty, Field(max_length=100)]], Field(min_length=1, max_length=4)]
    source_refs: Annotated[list[SourceRef], Field(max_length=6)] = Field(default_factory=list)


class RevisionNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[NonEmpty, Field(max_length=40)]
    overview: Annotated[NonEmpty, Field(max_length=100)]
    sections: Annotated[list[NotesSection], Field(min_length=1, max_length=6)]
    pitfalls: Annotated[list[Annotated[NonEmpty, Field(max_length=80)]], Field(max_length=4)]

    @model_validator(mode="after")
    def compact(self) -> "RevisionNotes":
        text = self.title + self.overview + "".join(section.heading + "".join(section.bullets) for section in self.sections) + "".join(self.pitfalls)
        if len(text) > 1600:
            raise ValueError("复习提纲超过1600字，必须压缩合并")
        return self


class MapNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Annotated[NonEmpty, Field(max_length=28)]
    relation: Annotated[NonEmpty, Field(max_length=12)]
    detail: Annotated[NonEmpty, Field(max_length=180)]
    children: Annotated[list["MapNode"], Field(max_length=6)]
    source_refs: Annotated[list[SourceRef], Field(max_length=6)] = Field(default_factory=list)


class RevisionMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[NonEmpty, Field(max_length=28)]
    overview: Annotated[NonEmpty, Field(max_length=140)]
    branches: Annotated[list[MapNode], Field(min_length=1, max_length=6)]

    @model_validator(mode="after")
    def hierarchy(self) -> "RevisionMap":
        count = 0

        def visit(nodes: list[MapNode], depth: int) -> None:
            nonlocal count
            if depth > 3 and nodes:
                raise ValueError("导图最多三层分支")
            if len({node.label for node in nodes}) != len(nodes):
                raise ValueError("同级主题不能重复")
            for node in nodes:
                count += 1
                visit(node.children, depth + 1)
        visit(self.branches, 1)
        if count > 65 or any(not branch.children for branch in self.branches):
            raise ValueError("导图须按主题归纳下级概念，总节点最多65个，不能平铺标题")
        return self


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
