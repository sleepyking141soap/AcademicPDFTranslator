"""Safe local storage for benchmark workspaces and annotation drafts."""

import hashlib
import json
import shutil
from pathlib import Path

from academic_pdf_translator.guard.academic_guard import AcademicGuard
from academic_pdf_translator.parser.pdf_parser import NativePDFParser
from academic_pdf_translator.pir.models import Document
from academic_pdf_translator.pir.serializer import atomic_write, load_document, save_document

from .models import (
    BenchmarkDocument,
    BenchmarkManifest,
    BlockAnnotation,
    DatasetSplit,
    DocumentAnnotation,
    ExpectedProtectedItem,
    PageAnnotation,
    TranslationVerdict,
)

MANIFEST_NAME = "manifest.json"


def _json_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def translation_hash(text: str) -> str:
    return text_hash(text) if text else ""


def document_fingerprint(document: Document) -> str:
    """Anchor labels to segmentation/text while allowing order and type changes."""
    blocks = sorted(
        (
            {
                "block_id": block.block_id,
                "page": block.page,
                "bbox": list(block.bbox),
                "text": block.text,
            }
            for block in document.blocks
        ),
        key=lambda item: item["block_id"],
    )
    return _json_hash({"document_id": document.document_id, "blocks": blocks})


def annotation_from_document(document: Document) -> DocumentAnnotation:
    guard = AcademicGuard()
    block_annotations: dict[str, BlockAnnotation] = {}
    for block in document.blocks:
        protected = guard.protect(block.text).items
        block_annotations[block.block_id] = BlockAnnotation(
            block_id=block.block_id,
            source_text_hash=text_hash(block.text),
            expected_block_type=block.block_type,
            expected_protected_items=[
                ExpectedProtectedItem(
                    kind=item.kind,
                    value=item.value,
                    start=item.start,
                    end=item.end,
                )
                for item in protected
            ],
        )
    return DocumentAnnotation(
        document_id=document.document_id,
        filename=document.filename,
        source_fingerprint=document_fingerprint(document),
        pages=[
            PageAnnotation(page=page.page, expected_order=[b.block_id for b in page.blocks])
            for page in document.pages
        ],
        blocks=block_annotations,
    )


def _manifest_path(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / MANIFEST_NAME


def resolve_workspace_path(workspace: str | Path, relative: str) -> Path:
    root = Path(workspace).resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path escapes benchmark workspace: {relative}")
    return candidate


def save_manifest(workspace: str | Path, manifest: BenchmarkManifest) -> Path:
    path = _manifest_path(workspace)
    atomic_write(path, manifest.model_dump_json(indent=2))
    return path


def load_workspace(workspace: str | Path) -> BenchmarkManifest:
    path = _manifest_path(workspace)
    if not path.is_file():
        raise ValueError(f"Benchmark workspace is not initialized: {path.parent}")
    return BenchmarkManifest.model_validate_json(path.read_text(encoding="utf-8"))


def init_workspace(workspace: str | Path, name: str, description: str = "") -> BenchmarkManifest:
    root = Path(workspace).resolve()
    path = root / MANIFEST_NAME
    if path.exists():
        raise ValueError(f"Benchmark workspace already exists: {root}")
    for directory in ("sources", "pir", "annotations", "reports"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    manifest = BenchmarkManifest(name=name, description=description)
    save_manifest(root, manifest)
    return manifest


def save_annotation(annotation: DocumentAnnotation, path: str | Path) -> Path:
    path = Path(path)
    atomic_write(path, annotation.model_dump_json(indent=2))
    return path


def load_annotation(path: str | Path) -> DocumentAnnotation:
    return DocumentAnnotation.model_validate_json(Path(path).read_text(encoding="utf-8"))


def add_document(
    workspace: str | Path,
    pdf_path: str | Path,
    *,
    pir_path: str | Path | None = None,
    split: DatasetSplit = DatasetSplit.CALIBRATION,
    domain: str = "",
    notes: str = "",
) -> BenchmarkDocument:
    root = Path(workspace).resolve()
    manifest = load_workspace(root)
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.is_file():
        raise ValueError(f"PDF not found: {pdf_path}")
    document = load_document(pir_path) if pir_path else NativePDFParser().parse(pdf_path)
    expected_id = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:20]
    if document.document_id != expected_id:
        raise ValueError("PIR document ID does not match the supplied PDF")
    if any(item.document_id == document.document_id for item in manifest.documents):
        raise ValueError(f"Document is already in the workspace: {document.document_id}")

    source_relative = f"sources/{document.document_id}.pdf"
    pir_relative = f"pir/{document.document_id}.json"
    annotation_relative = f"annotations/{document.document_id}.json"
    shutil.copyfile(pdf_path, resolve_workspace_path(root, source_relative))
    save_document(document, resolve_workspace_path(root, pir_relative))
    save_annotation(
        annotation_from_document(document), resolve_workspace_path(root, annotation_relative)
    )
    entry = BenchmarkDocument(
        document_id=document.document_id,
        filename=pdf_path.name,
        source_pdf=source_relative,
        pir=pir_relative,
        annotation=annotation_relative,
        split=split,
        domain=domain,
        notes=notes,
    )
    manifest.documents.append(entry)
    save_manifest(root, manifest)
    return entry


def validate_annotation(document: Document, annotation: DocumentAnnotation) -> list[str]:
    errors: list[str] = []
    if annotation.document_id != document.document_id:
        errors.append("Annotation document_id does not match PIR")
    if annotation.source_fingerprint != document_fingerprint(document):
        errors.append("PIR segmentation/text changed; migrate or recreate the annotation")
    blocks = {block.block_id: block for block in document.blocks}
    pages = {page.page: page for page in document.pages}
    if set(annotation.blocks) != set(blocks):
        errors.append("Annotation block IDs do not match PIR block IDs")
    for block_id, label in annotation.blocks.items():
        block = blocks.get(block_id)
        if not block:
            continue
        if label.source_text_hash != text_hash(block.text):
            errors.append(f"{block_id}: source text changed")
        for item in label.expected_protected_items:
            if item.end > len(block.text) or block.text[item.start : item.end] != item.value:
                errors.append(f"{block_id}: protected span does not match source text")
        review = label.translation
        if review.verdict != TranslationVerdict.NOT_REVIEWED:
            current_hash = translation_hash(block.translation)
            if not review.translation_hash:
                errors.append(f"{block_id}: reviewed translation has no translation hash")
            elif review.translation_hash != current_hash:
                errors.append(f"{block_id}: translation changed after human review")
    annotation_pages = {page.page: page for page in annotation.pages}
    if set(annotation_pages) != set(pages):
        errors.append("Annotation page numbers do not match PIR pages")
    for page_number, page_label in annotation_pages.items():
        page = pages.get(page_number)
        if not page:
            continue
        predicted_ids = {block.block_id for block in page.blocks}
        if len(page_label.expected_order) != len(set(page_label.expected_order)):
            errors.append(f"Page {page_number}: expected order contains duplicates")
        if set(page_label.expected_order) != predicted_ids:
            errors.append(f"Page {page_number}: expected order must contain every page block once")
    return errors
