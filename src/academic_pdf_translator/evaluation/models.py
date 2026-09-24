"""Versioned contracts for local benchmark manifests and human annotations."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from academic_pdf_translator.pir.models import BlockType


class DatasetSplit(StrEnum):
    CALIBRATION = "calibration"
    TEST = "test"


class TranslationVerdict(StrEnum):
    NOT_REVIEWED = "not_reviewed"
    PASS = "pass"
    MINOR_ERROR = "minor_error"
    MAJOR_ERROR = "major_error"
    UNUSABLE = "unusable"


class TranslationErrorTag(StrEnum):
    MISTRANSLATION = "mistranslation"
    OMISSION = "omission"
    ADDITION = "addition"
    TERMINOLOGY = "terminology"
    NEGATION = "negation"
    COMPARISON = "comparison"
    ENTITY_RELATION = "entity_relation"
    NUMBER_UNIT = "number_unit"
    CITATION = "citation"
    FLUENCY = "fluency"
    OTHER = "other"


class SegmentationIssue(StrEnum):
    MISSING_TEXT = "missing_text"
    OVER_SPLIT = "over_split"
    OVER_MERGED = "over_merged"
    SPURIOUS_BLOCK = "spurious_block"
    CROSS_PAGE_SPLIT = "cross_page_split"
    OTHER = "other"


class ExpectedProtectedItem(BaseModel):
    kind: str = Field(min_length=1)
    value: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_range(self) -> "ExpectedProtectedItem":
        if self.end <= self.start:
            raise ValueError("Protected item end must be greater than start")
        return self


class TranslationReview(BaseModel):
    verdict: TranslationVerdict = TranslationVerdict.NOT_REVIEWED
    error_tags: list[TranslationErrorTag] = Field(default_factory=list)
    corrected_translation: str = ""
    notes: str = ""
    translation_hash: str = ""


class BlockAnnotation(BaseModel):
    block_id: str
    source_text_hash: str
    expected_block_type: BlockType
    block_type_reviewed: bool = False
    protection_reviewed: bool = False
    expected_protected_items: list[ExpectedProtectedItem] = Field(default_factory=list)
    translation: TranslationReview = Field(default_factory=TranslationReview)
    notes: str = ""


class PageAnnotation(BaseModel):
    page: int = Field(ge=1)
    reading_order_reviewed: bool = False
    segmentation_reviewed: bool = False
    segmentation_issues: list[SegmentationIssue] = Field(default_factory=list)
    expected_order: list[str] = Field(default_factory=list)
    notes: str = ""


class DocumentAnnotation(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    document_id: str = Field(pattern=r"^[0-9a-f]{20}$")
    filename: str
    source_fingerprint: str
    annotator: str = ""
    status: Literal["not_started", "in_progress", "complete"] = "not_started"
    pages: list[PageAnnotation] = Field(default_factory=list)
    blocks: dict[str, BlockAnnotation] = Field(default_factory=dict)
    notes: str = ""


class BenchmarkDocument(BaseModel):
    document_id: str = Field(pattern=r"^[0-9a-f]{20}$")
    filename: str
    source_pdf: str
    pir: str
    annotation: str
    split: DatasetSplit = DatasetSplit.CALIBRATION
    domain: str = ""
    notes: str = ""


class BenchmarkManifest(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    name: str = Field(min_length=1)
    description: str = ""
    documents: list[BenchmarkDocument] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_documents(self) -> "BenchmarkManifest":
        identifiers = [item.document_id for item in self.documents]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Manifest contains duplicate document IDs")
        return self


class MetricSummary(BaseModel):
    dataset_name: str
    documents: int
    completed_documents: int
    pages_reviewed: int
    segmentation_pages_reviewed: int
    block_types_reviewed: int
    translations_reviewed: int
    reading_order_pair_accuracy: float | None = None
    segmentation_issue_page_rate: float | None = None
    segmentation_issues: dict[str, int] = Field(default_factory=dict)
    block_type_accuracy: float | None = None
    guard_precision: float | None = None
    guard_recall: float | None = None
    guard_f1: float | None = None
    translation_pass_rate: float | None = None
    translation_acceptable_rate: float | None = None
    translation_major_error_rate: float | None = None
    translation_error_tags: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
