"""Adapters for OCR, MinerU, Docling and native/vision fusion can share PIR."""

from pathlib import Path
from typing import Protocol

from academic_pdf_translator.pir.models import Document, Page


class PaperParser(Protocol):
    def parse(self, path: str | Path) -> Document: ...


class PageEnricher(Protocol):
    """Future OCR/vision adapter; keep coordinates in PDF page points."""

    def enrich(self, pdf_path: Path, page: Page) -> Page: ...


class PageFusion(Protocol):
    def fuse(self, native: Page, alternative: Page) -> Page: ...
