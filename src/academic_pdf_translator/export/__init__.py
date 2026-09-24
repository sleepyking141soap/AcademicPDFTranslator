"""Portable PIR JSON and standalone bilingual HTML outputs."""

from pathlib import Path

from academic_pdf_translator.pir.models import Document

from .html_exporter import export_html
from .json_exporter import export_json


def export_document(document: Document, directory: str | Path) -> tuple[Path, Path]:
    directory = Path(directory)
    return export_json(document, directory / "document.json"), export_html(
        document, directory / "document.html"
    )
