"""Serializable contracts shared by parsing, translation, verification and explanation."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

BBox = tuple[float, float, float, float]


class BlockType(StrEnum):
    TITLE = "title"
    SECTION_TITLE = "section_title"
    PARAGRAPH = "paragraph"
    CAPTION = "caption"
    TABLE = "table"
    EQUATION = "equation"
    REFERENCE = "reference"
    HEADER = "header"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class Span(BaseModel):
    text: str
    bbox: BBox
    font_size: float
    font_name: str
    flags: int = 0


class Line(BaseModel):
    text: str
    bbox: BBox
    spans: list[Span] = Field(default_factory=list)
    direction: tuple[float, float] = (1.0, 0.0)


class ProtectedItem(BaseModel):
    placeholder: str
    kind: str
    value: str
    start: int
    end: int


class CheckError(BaseModel):
    type: str
    source: str = ""
    translation: str = ""
    message: str = ""


class CheckResult(BaseModel):
    passed: bool
    risk_score: float = Field(ge=0, le=1)
    errors: list[CheckError] = Field(default_factory=list)
    scope: str = "Deterministic token consistency only; not semantic accuracy."


class TermExplanation(BaseModel):
    term: str
    explanation: str


class Explanation(BaseModel):
    original: str
    translation: str
    plain_explanation: str
    role_in_paper: str
    key_terms: list[TermExplanation] = Field(default_factory=list)
    warning: str = "LLM interpretation; verify against the paper."


class ProcessingStats(BaseModel):
    provider_calls: int = 0
    cache_hits: int = 0
    resumed_blocks: int = 0
    retained_blocks: int = 0
    failed_blocks: int = 0


class Block(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    block_id: str
    block_type: BlockType = BlockType.UNKNOWN
    bbox: BBox
    section: str = ""
    source: Literal["native", "ocr", "vision", "fused"] = "native"
    text: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    lines: list[Line] = Field(default_factory=list)
    native_block_number: int | None = None
    protected_items: list[ProtectedItem] = Field(default_factory=list)
    protected_text: str = ""
    raw_translation: str = ""
    translation: str = ""
    translation_status: Literal["pending", "translated", "retained", "failed", "demo"] = "pending"
    translation_origin: Literal["none", "provider", "cache", "resume", "retained", "demo"] = "none"
    warnings: list[str] = Field(default_factory=list)
    check: CheckResult | None = None
    explanation: Explanation | None = None


class Page(BaseModel):
    page: int
    width: float
    height: float
    requires_ocr: bool = False
    layout: Literal["single_column", "two_column", "uncertain"] = "single_column"
    warnings: list[str] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)


class Document(BaseModel):
    schema_version: Literal["0.1", "0.2"] = "0.2"
    document_id: str
    filename: str
    title: str = ""
    target_language: str = "Simplified Chinese"
    model: str = ""
    mode: Literal["live", "demo", "parse_only"] = "parse_only"
    status: Literal["parsed", "completed", "partial", "failed"] = "parsed"
    warnings: list[str] = Field(default_factory=list)
    processing: ProcessingStats = Field(default_factory=ProcessingStats)
    pages: list[Page] = Field(default_factory=list)

    @property
    def blocks(self) -> list[Block]:
        """Return blocks in document reading order."""
        return [block for page in self.pages for block in page.blocks]

    def block(self, block_id: str) -> Block:
        """Resolve a stable block identifier or raise KeyError."""
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        raise KeyError(f"Unknown block: {block_id}")
