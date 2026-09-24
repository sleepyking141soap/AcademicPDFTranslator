"""Local Streamlit UI for reviewing layout, guard spans and translations."""

import os
from pathlib import Path

import pymupdf
import streamlit as st

from academic_pdf_translator.evaluation.models import (
    ExpectedProtectedItem,
    SegmentationIssue,
    TranslationErrorTag,
    TranslationReview,
    TranslationVerdict,
)
from academic_pdf_translator.evaluation.storage import (
    load_annotation,
    load_workspace,
    resolve_workspace_path,
    save_annotation,
    translation_hash,
    validate_annotation,
)
from academic_pdf_translator.pir.models import BlockType
from academic_pdf_translator.pir.serializer import load_document


def _records(value: object) -> list[dict[str, object]]:
    if hasattr(value, "to_dict"):
        return value.to_dict("records")  # type: ignore[no-any-return, union-attr]
    return list(value)  # type: ignore[arg-type]


def _page_png(path: Path, page_number: int) -> bytes:
    with pymupdf.open(path) as pdf:
        page = pdf[page_number - 1]
        return page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False).tobytes("png")


def _mark_in_progress(annotation) -> None:
    if annotation.status == "not_started":
        annotation.status = "in_progress"


def main() -> None:
    st.set_page_config(page_title="AcademicPDFTranslator Annotation", page_icon="🧪", layout="wide")
    st.title("AcademicPDFTranslator · 人工标注")
    workspace = Path(os.environ.get("APT_BENCHMARK_WORKSPACE", "benchmark/workspace")).resolve()
    try:
        manifest = load_workspace(workspace)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        st.code(
            "python benchmark.py init benchmark/workspace\n"
            "python benchmark.py add benchmark/workspace paper.pdf"
        )
        return
    if not manifest.documents:
        st.info("工作区还没有论文。请先用 benchmark add 添加 PDF。")
        return

    labels = {
        entry.document_id: f"{entry.filename} · {entry.domain or '未分类'} · {entry.split.value}"
        for entry in manifest.documents
    }
    selected_id = st.sidebar.selectbox("论文", list(labels), format_func=labels.get)
    entry = next(item for item in manifest.documents if item.document_id == selected_id)
    document = load_document(resolve_workspace_path(workspace, entry.pir))
    annotation_path = resolve_workspace_path(workspace, entry.annotation)
    annotation = load_annotation(annotation_path)
    pdf_path = resolve_workspace_path(workspace, entry.source_pdf)

    annotator = st.sidebar.text_input("标注人", annotation.annotator)
    status_options = ["not_started", "in_progress", "complete"]
    status = st.sidebar.selectbox(
        "文档状态", status_options, index=status_options.index(annotation.status)
    )
    notes = st.sidebar.text_area("文档备注", annotation.notes)
    if st.sidebar.button("保存文档信息"):
        annotation.annotator = annotator.strip()
        annotation.status = status
        annotation.notes = notes
        save_annotation(annotation, annotation_path)
        st.sidebar.success("已保存")

    validation_errors = validate_annotation(document, annotation)
    if validation_errors:
        for error in validation_errors:
            st.error(error)
        st.stop()

    layout_tab, block_tab, guide_tab = st.tabs(["版面与阅读顺序", "保护项与翻译", "标注说明"])
    with layout_tab:
        page_number = st.selectbox("页码", [page.page for page in document.pages])
        page = next(page for page in document.pages if page.page == page_number)
        page_label = next(item for item in annotation.pages if item.page == page_number)
        preview, editor = st.columns([1, 1])
        preview.image(_page_png(pdf_path, page_number), caption=f"第 {page_number} 页")
        rows = []
        expected_positions = {
            block_id: index + 1 for index, block_id in enumerate(page_label.expected_order)
        }
        for index, block in enumerate(page.blocks, start=1):
            label = annotation.blocks[block.block_id]
            rows.append(
                {
                    "order": expected_positions.get(block.block_id, index),
                    "block_id": block.block_id,
                    "expected_type": label.expected_block_type.value,
                    "type_reviewed": label.block_type_reviewed,
                    "text": block.text.replace("\n", " ")[:160],
                }
            )
        with editor:
            st.caption("修改 order 调整人工阅读顺序；确认类型后勾选 type_reviewed。")
            edited = st.data_editor(
                rows,
                hide_index=True,
                disabled=["block_id", "text"],
                column_config={
                    "expected_type": st.column_config.SelectboxColumn(
                        "expected_type", options=[item.value for item in BlockType], required=True
                    ),
                    "type_reviewed": st.column_config.CheckboxColumn("type_reviewed"),
                    "text": st.column_config.TextColumn("text", width="large"),
                },
                key=f"layout-{selected_id}-{page_number}",
            )
            reviewed = st.checkbox(
                "本页阅读顺序已人工确认",
                value=page_label.reading_order_reviewed,
                key=f"order-reviewed-{selected_id}-{page_number}",
            )
            segmentation_reviewed = st.checkbox(
                "本页分块完整性已人工确认",
                value=page_label.segmentation_reviewed,
                key=f"segmentation-reviewed-{selected_id}-{page_number}",
            )
            segmentation_issue_values = [item.value for item in SegmentationIssue]
            segmentation_issues = st.multiselect(
                "分块问题",
                segmentation_issue_values,
                default=[item.value for item in page_label.segmentation_issues],
                key=f"segmentation-issues-{selected_id}-{page_number}",
            )
            page_notes = st.text_area(
                "本页备注", page_label.notes, key=f"page-notes-{selected_id}-{page_number}"
            )
            if st.button("保存本页标注", type="primary"):
                records = _records(edited)
                records.sort(key=lambda row: int(row["order"]))
                page_label.expected_order = [str(row["block_id"]) for row in records]
                page_label.reading_order_reviewed = reviewed
                page_label.segmentation_reviewed = segmentation_reviewed
                page_label.segmentation_issues = [
                    SegmentationIssue(item) for item in segmentation_issues
                ]
                page_label.notes = page_notes
                for row in records:
                    label = annotation.blocks[str(row["block_id"])]
                    label.expected_block_type = BlockType(str(row["expected_type"]))
                    label.block_type_reviewed = bool(row["type_reviewed"])
                _mark_in_progress(annotation)
                save_annotation(annotation, annotation_path)
                st.success("本页标注已保存")

    with block_tab:
        block_ids = [block.block_id for block in document.blocks]
        selected_block_id = st.selectbox(
            "文本块",
            block_ids,
            format_func=lambda value: f"{value} · {document.block(value).text[:80]}",
        )
        block = document.block(selected_block_id)
        label = annotation.blocks[selected_block_id]
        source, translation = st.columns(2)
        source.subheader("原文")
        source.text(block.text)
        translation.subheader("当前译文")
        translation.text(block.translation or "当前 PIR 没有译文；可先完成版面和保护项标注。")

        st.subheader("AcademicGuard 保护项")
        st.caption("预填内容来自当前规则。请删除误保护项、补充漏项，然后勾选已确认。")
        span_rows = [item.model_dump() for item in label.expected_protected_items]
        edited_spans = st.data_editor(
            span_rows,
            num_rows="dynamic",
            hide_index=True,
            key=f"spans-{selected_id}-{selected_block_id}",
        )
        protection_reviewed = st.checkbox(
            "本块保护项已人工确认",
            value=label.protection_reviewed,
            key=f"protection-reviewed-{selected_id}-{selected_block_id}",
        )
        if st.button("保存保护项"):
            try:
                items = [
                    ExpectedProtectedItem.model_validate(row) for row in _records(edited_spans)
                ]
                for item in items:
                    if (
                        item.end > len(block.text)
                        or block.text[item.start : item.end] != item.value
                    ):
                        raise ValueError(
                            f"{item.kind} {item.value!r} 的 start/end 与原文位置不一致"
                        )
                label.expected_protected_items = items
                label.protection_reviewed = protection_reviewed
                _mark_in_progress(annotation)
                save_annotation(annotation, annotation_path)
                st.success("保护项已保存")
            except ValueError as exc:
                st.error(str(exc))

        st.subheader("翻译质量")
        verdict_values = [item.value for item in TranslationVerdict]
        verdict = st.selectbox(
            "结论",
            verdict_values,
            index=verdict_values.index(label.translation.verdict.value),
            key=f"verdict-{selected_id}-{selected_block_id}",
        )
        tag_values = [item.value for item in TranslationErrorTag]
        selected_tags = st.multiselect(
            "错误标签",
            tag_values,
            default=[item.value for item in label.translation.error_tags],
            key=f"tags-{selected_id}-{selected_block_id}",
        )
        correction = st.text_area(
            "建议译文（可选）",
            label.translation.corrected_translation,
            key=f"correction-{selected_id}-{selected_block_id}",
        )
        review_notes = st.text_area(
            "翻译备注",
            label.translation.notes,
            key=f"review-notes-{selected_id}-{selected_block_id}",
        )
        if st.button("保存翻译评审"):
            if verdict != TranslationVerdict.NOT_REVIEWED.value and not block.translation:
                st.error("当前块没有译文，不能标记翻译质量。请导入真实翻译 PIR。")
            else:
                label.translation = TranslationReview(
                    verdict=TranslationVerdict(verdict),
                    error_tags=[TranslationErrorTag(item) for item in selected_tags],
                    corrected_translation=correction,
                    notes=review_notes,
                    translation_hash=(
                        translation_hash(block.translation)
                        if verdict != TranslationVerdict.NOT_REVIEWED.value
                        else ""
                    ),
                )
                _mark_in_progress(annotation)
                save_annotation(annotation, annotation_path)
                st.success("翻译评审已保存")

    with guide_tab:
        st.markdown(
            """
            ### 建议顺序

            1. 先检查漏块、误拆、误合并和跨页断开，再确认阅读顺序。
            2. 确认块类型。标题、正文、图表说明和参考文献是首批重点。
            3. 检查 AcademicGuard 预填项，删除误报并补充漏报。
            4. 只有当前 PIR 含真实模型译文时，才评价翻译质量。

            `pass` 表示没有实质错误；`minor_error` 表示不影响主要含义的局部问题；
            `major_error` 表示结论、条件、对象或关键术语存在实质偏差；`unusable` 表示需要重译。
            不确定时写备注，不要猜测。
            """
        )


if __name__ == "__main__":
    main()
