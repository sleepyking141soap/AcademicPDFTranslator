"""Extract native text, original spans and PDF-space geometry with PyMuPDF."""

import hashlib
import logging
import re
from collections import Counter
from pathlib import Path

import pymupdf

from academic_pdf_translator.pir.models import Block, BlockType, Document, Line, Page, Span

from .block_classifier import classify
from .layout import reading_order

logger = logging.getLogger(__name__)


class PDFParseError(ValueError):
    """Unreadable, encrypted or unsupported PDF input."""


def _join_lines(lines: list[Line]) -> str:
    # Keep hyphens: guessing dehyphenation can silently change scientific names.
    return "\n".join(line.text for line in lines).strip()


class NativePDFParser:
    def parse(self, path: str | Path) -> Document:
        path = Path(path)
        if not path.is_file():
            raise PDFParseError(f"PDF not found: {path}")
        document_id = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
        document = Document(document_id=document_id, filename=path.name)
        try:
            with pymupdf.open(path) as pdf:
                if not pdf.is_pdf:
                    raise PDFParseError("Input is not a PDF")
                if pdf.needs_pass:
                    raise PDFParseError("Encrypted PDF requires an unlocked local copy")
                for index, pdf_page in enumerate(pdf):
                    page = self._page(pdf_page, index + 1, document_id)
                    document.pages.append(page)
        except (pymupdf.FileDataError, RuntimeError) as exc:
            raise PDFParseError("Cannot read PDF; check whether the file is damaged") from exc
        if not document.pages:
            raise PDFParseError("PDF has no pages")
        self._classify(document)
        titles = [b.text for b in document.blocks if b.block_type == BlockType.TITLE]
        document.title = " ".join(titles) or path.stem
        if any(page.requires_ocr for page in document.pages):
            document.warnings.append(
                "Some pages require OCR. Native-only mode processes their available text."
            )
        logger.info(
            "Parsed %s: %d pages, %d blocks", path.name, len(document.pages), len(document.blocks)
        )
        return document

    def _page(self, pdf_page: pymupdf.Page, page_number: int, document_id: str) -> Page:
        # get_text geometry is in unrotated page coordinates.
        page = Page(page=page_number, width=pdf_page.cropbox.width, height=pdf_page.cropbox.height)
        data = pdf_page.get_text(
            "dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES, sort=False
        )
        for raw in data["blocks"]:
            if raw["type"] != 0:
                continue
            groups: list[list[Line]] = [[]]
            for raw_line in raw.get("lines", []):
                spans = [
                    Span(
                        text=s["text"],
                        bbox=tuple(s["bbox"]),
                        font_size=s["size"],
                        font_name=s["font"],
                        flags=s["flags"],
                    )
                    for s in raw_line["spans"]
                ]
                line = Line(
                    text="".join(s.text for s in spans),
                    bbox=tuple(raw_line["bbox"]),
                    spans=spans,
                    direction=tuple(raw_line.get("dir", (1, 0))),
                )
                if not line.text.strip():
                    continue
                if groups[-1]:
                    previous = groups[-1][-1]
                    size = max((s.font_size for s in previous.spans), default=10)
                    # Split blocks that merge parallel columns or separated paragraphs.
                    if (
                        abs(line.bbox[0] - previous.bbox[0]) > page.width * 0.35
                        or line.bbox[1] < previous.bbox[1] - 3
                        or line.bbox[1] - previous.bbox[3] > size
                    ):
                        groups.append([])
                groups[-1].append(line)
            for part, lines in enumerate(groups):
                if not lines:
                    continue
                bbox = (
                    min(line.bbox[0] for line in lines),
                    min(line.bbox[1] for line in lines),
                    max(line.bbox[2] for line in lines),
                    max(line.bbox[3] for line in lines),
                )
                block = Block(
                    document_id=document_id,
                    page=page_number,
                    block_id=f"p{page_number:04d}-b{raw['number']:04d}-{part}",
                    bbox=bbox,
                    text=_join_lines(lines),
                    lines=lines,
                    native_block_number=raw["number"],
                    confidence=0.85,
                )
                if any(abs(line.direction[1]) > 0.1 for line in lines):
                    block.confidence = 0.4
                    block.warnings.append("RotatedText: reading order requires review")
                page.blocks.append(block)
        page.blocks, layout = reading_order(page.blocks, page.width, page.height)
        page.layout = layout
        if layout == "uncertain":
            page.warnings.append("Reading order is uncertain; inspect block coordinates")
        text = "".join(b.text for b in page.blocks)
        meaningful = sum(c.isalnum() for c in text)
        page.requires_ocr = meaningful < 20 or text.count("\ufffd") > max(1, len(text) * 0.1)
        if page.requires_ocr:
            page.warnings.append("RequiresOCR: missing, sparse or unusable native text layer")
        return page

    def _classify(self, document: Document) -> None:
        font_weights: Counter[float] = Counter()
        margins: Counter[str] = Counter()

        def signature(text: str) -> str:
            return re.sub(r"\d+", "#", text.strip().lower())

        for page in document.pages:
            page_margins = set()
            for block in page.blocks:
                for line in block.lines:
                    for span in line.spans:
                        font_weights[round(span.font_size, 1)] += len(span.text)
                if block.bbox[3] < page.height * 0.07 or block.bbox[1] > page.height * 0.93:
                    page_margins.add(signature(block.text))
            margins.update(page_margins)
        body_size = font_weights.most_common(1)[0][0] if font_weights else 10.0
        section = ""
        references = False
        for page in document.pages:
            for block in page.blocks:
                block.block_type = classify(block, body_size, page.height)
                if margins[signature(block.text)] >= 2:
                    if block.bbox[3] < page.height * 0.07:
                        block.block_type = BlockType.HEADER
                    elif block.bbox[1] > page.height * 0.93:
                        block.block_type = BlockType.FOOTER
                if block.block_type == BlockType.SECTION_TITLE:
                    section = block.text.replace("\n", " ")
                    references = bool(re.search(r"\b(references|bibliography)\b", section, re.I))
                elif references and block.block_type not in (BlockType.HEADER, BlockType.FOOTER):
                    block.block_type = BlockType.REFERENCE
                block.section = section
