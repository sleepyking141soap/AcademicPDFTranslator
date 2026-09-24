from pathlib import Path

import pytest

from academic_pdf_translator.evaluation.metrics import evaluate_workspace
from academic_pdf_translator.evaluation.models import TranslationReview, TranslationVerdict
from academic_pdf_translator.evaluation.storage import (
    add_document,
    init_workspace,
    load_annotation,
    load_workspace,
    resolve_workspace_path,
    save_annotation,
    translation_hash,
    validate_annotation,
)
from academic_pdf_translator.parser.pdf_parser import NativePDFParser
from academic_pdf_translator.pir.serializer import load_document, save_document


def _workspace_with_translated_pir(tmp_path: Path, sample_pdf: Path):
    workspace = tmp_path / "benchmark"
    init_workspace(workspace, "Calibration")
    document = NativePDFParser().parse(sample_pdf)
    document.blocks[0].translation = "测试译文"
    document.blocks[0].translation_status = "translated"
    pir_path = tmp_path / "translated.json"
    save_document(document, pir_path)
    entry = add_document(workspace, sample_pdf, pir_path=pir_path, domain="test")
    return workspace, entry


def test_workspace_add_validate_and_evaluate(tmp_path, sample_pdf):
    workspace, entry = _workspace_with_translated_pir(tmp_path, sample_pdf)
    manifest = load_workspace(workspace)
    assert manifest.name == "Calibration"
    assert manifest.documents == [entry]
    assert (
        resolve_workspace_path(workspace, entry.source_pdf).read_bytes() == sample_pdf.read_bytes()
    )

    document = load_document(resolve_workspace_path(workspace, entry.pir))
    annotation_path = resolve_workspace_path(workspace, entry.annotation)
    annotation = load_annotation(annotation_path)
    assert not validate_annotation(document, annotation)

    page_label = annotation.pages[0]
    page_label.reading_order_reviewed = True
    page_label.segmentation_reviewed = True
    page_label.expected_order.reverse()
    first = document.pages[0].blocks[0]
    first_label = annotation.blocks[first.block_id]
    first_label.block_type_reviewed = True
    first_label.protection_reviewed = True
    first_label.translation = TranslationReview(
        verdict=TranslationVerdict.PASS,
        translation_hash=translation_hash(first.translation),
    )
    annotation.status = "complete"
    save_annotation(annotation, annotation_path)

    summary = evaluate_workspace(workspace)
    assert summary.documents == 1
    assert summary.completed_documents == 1
    assert summary.pages_reviewed == 1
    assert summary.segmentation_pages_reviewed == 1
    assert summary.segmentation_issue_page_rate == 0
    assert summary.block_types_reviewed == 1
    assert summary.block_type_accuracy == 1
    assert summary.reading_order_pair_accuracy == 0
    assert summary.guard_precision == 1
    assert summary.guard_recall == 1
    assert summary.guard_f1 == 1
    assert summary.translations_reviewed == 1
    assert summary.translation_pass_rate == 1
    assert summary.translation_acceptable_rate == 1
    assert summary.translation_major_error_rate == 0
    assert not summary.warnings


def test_changed_translation_invalidates_review(tmp_path, sample_pdf):
    workspace, entry = _workspace_with_translated_pir(tmp_path, sample_pdf)
    document_path = resolve_workspace_path(workspace, entry.pir)
    annotation_path = resolve_workspace_path(workspace, entry.annotation)
    document = load_document(document_path)
    annotation = load_annotation(annotation_path)
    block = document.blocks[0]
    annotation.blocks[block.block_id].translation = TranslationReview(
        verdict=TranslationVerdict.MINOR_ERROR,
        translation_hash=translation_hash(block.translation),
    )
    save_annotation(annotation, annotation_path)

    block.translation = "已经变化的译文"
    save_document(document, document_path)
    errors = validate_annotation(document, load_annotation(annotation_path))
    assert any("translation changed" in error for error in errors)
    summary = evaluate_workspace(workspace)
    assert summary.translations_reviewed == 0
    assert summary.warnings


def test_rejects_pir_for_another_pdf(tmp_path, sample_pdf):
    workspace = tmp_path / "benchmark"
    init_workspace(workspace, "Calibration")
    document = NativePDFParser().parse(sample_pdf)
    document.document_id = "0" * 20
    pir_path = tmp_path / "wrong.json"
    save_document(document, pir_path)
    with pytest.raises(ValueError, match="does not match"):
        add_document(workspace, sample_pdf, pir_path=pir_path)


def test_workspace_path_cannot_escape(tmp_path):
    workspace = tmp_path / "benchmark"
    init_workspace(workspace, "Calibration")
    with pytest.raises(ValueError, match="escapes"):
        resolve_workspace_path(workspace, "../outside.json")
