"""Deterministic metrics over reviewed benchmark annotations."""

from collections import Counter
from pathlib import Path

from academic_pdf_translator.guard.academic_guard import AcademicGuard
from academic_pdf_translator.pir.serializer import atomic_write, load_document

from .models import MetricSummary, TranslationVerdict
from .storage import load_annotation, load_workspace, resolve_workspace_path, validate_annotation


def _order_pairs(order: list[str]) -> set[tuple[str, str]]:
    return {(left, right) for index, left in enumerate(order) for right in order[index + 1 :]}


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def evaluate_workspace(workspace: str | Path) -> MetricSummary:
    root = Path(workspace).resolve()
    manifest = load_workspace(root)
    pages_reviewed = 0
    segmentation_pages_reviewed = 0
    pages_with_segmentation_issues = 0
    segmentation_issues: Counter[str] = Counter()
    correct_order_pairs = 0
    total_order_pairs = 0
    type_correct = 0
    type_total = 0
    guard_true_positive = 0
    guard_predicted = 0
    guard_expected = 0
    verdicts: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    completed = 0
    warnings: list[str] = []
    guard = AcademicGuard()

    for entry in manifest.documents:
        document = load_document(resolve_workspace_path(root, entry.pir))
        annotation = load_annotation(resolve_workspace_path(root, entry.annotation))
        errors = validate_annotation(document, annotation)
        if errors:
            warnings.extend(f"{entry.document_id}: {error}" for error in errors)
            continue
        if annotation.status == "complete":
            completed += 1
        page_labels = {page.page: page for page in annotation.pages}
        for page in document.pages:
            label = page_labels[page.page]
            if label.segmentation_reviewed:
                segmentation_pages_reviewed += 1
                pages_with_segmentation_issues += int(bool(label.segmentation_issues))
                segmentation_issues.update(item.value for item in label.segmentation_issues)
            if not label.reading_order_reviewed:
                continue
            pages_reviewed += 1
            predicted = [block.block_id for block in page.blocks]
            expected_pairs = _order_pairs(label.expected_order)
            predicted_pairs = _order_pairs(predicted)
            total_order_pairs += len(expected_pairs)
            correct_order_pairs += len(expected_pairs & predicted_pairs)
        for block in document.blocks:
            label = annotation.blocks[block.block_id]
            if label.block_type_reviewed:
                type_total += 1
                type_correct += int(label.expected_block_type == block.block_type)
            if label.protection_reviewed:
                predicted = {
                    (item.kind, item.value, item.start, item.end)
                    for item in guard.protect(block.text).items
                }
                expected = {
                    (item.kind, item.value, item.start, item.end)
                    for item in label.expected_protected_items
                }
                guard_predicted += len(predicted)
                guard_expected += len(expected)
                guard_true_positive += len(predicted & expected)
            verdict = label.translation.verdict
            if verdict != TranslationVerdict.NOT_REVIEWED:
                verdicts[verdict.value] += 1
                tags.update(tag.value for tag in label.translation.error_tags)

    precision = _safe_ratio(guard_true_positive, guard_predicted)
    recall = _safe_ratio(guard_true_positive, guard_expected)
    f1 = None
    if precision is not None and recall is not None:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    reviewed_translations = sum(verdicts.values())
    major = (
        verdicts[TranslationVerdict.MAJOR_ERROR.value] + verdicts[TranslationVerdict.UNUSABLE.value]
    )
    summary = MetricSummary(
        dataset_name=manifest.name,
        documents=len(manifest.documents),
        completed_documents=completed,
        pages_reviewed=pages_reviewed,
        segmentation_pages_reviewed=segmentation_pages_reviewed,
        block_types_reviewed=type_total,
        translations_reviewed=reviewed_translations,
        reading_order_pair_accuracy=_safe_ratio(correct_order_pairs, total_order_pairs),
        segmentation_issue_page_rate=_safe_ratio(
            pages_with_segmentation_issues, segmentation_pages_reviewed
        ),
        segmentation_issues=dict(sorted(segmentation_issues.items())),
        block_type_accuracy=_safe_ratio(type_correct, type_total),
        guard_precision=precision,
        guard_recall=recall,
        guard_f1=f1,
        translation_pass_rate=_safe_ratio(
            verdicts[TranslationVerdict.PASS.value], reviewed_translations
        ),
        translation_acceptable_rate=_safe_ratio(
            verdicts[TranslationVerdict.PASS.value]
            + verdicts[TranslationVerdict.MINOR_ERROR.value],
            reviewed_translations,
        ),
        translation_major_error_rate=_safe_ratio(major, reviewed_translations),
        translation_error_tags=dict(sorted(tags.items())),
        warnings=warnings,
    )
    return summary


def save_report(summary: MetricSummary, path: str | Path) -> Path:
    path = Path(path)
    atomic_write(path, summary.model_dump_json(indent=2))
    return path
