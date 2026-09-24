"""Local Streamlit workflow with on-demand explanation and portable downloads."""

import re
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from academic_pdf_translator.config import Settings
from academic_pdf_translator.explain.paper_explain import PaperExplain
from academic_pdf_translator.export import export_document
from academic_pdf_translator.export.html_exporter import render_html
from academic_pdf_translator.pipeline import TranslationPipeline
from academic_pdf_translator.pir.models import Document
from academic_pdf_translator.pir.serializer import load_document
from academic_pdf_translator.translation.base import TranslationError
from academic_pdf_translator.translation.cache import FileTranslationCache
from academic_pdf_translator.translation.demo import DemoTranslator
from academic_pdf_translator.translation.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleTranslator,
)


def persist(document: Document) -> None:
    """UI results are scoped by content hash; never use an uploaded path as a filename."""
    if not re.fullmatch(r"[0-9a-f]{20}", document.document_id):
        raise ValueError("Unsupported document ID; expected a 20-character PDF content hash")
    export_document(document, Path("output") / document.document_id)


def main() -> None:
    st.set_page_config(page_title="AcademicPDFTranslator", page_icon="📖", layout="wide")
    st.title("AcademicPDFTranslator")
    st.caption("v0.2-dev · Native PDF Parsing / AcademicGuard / TransCheck / PaperExplain")
    try:
        settings = Settings.from_env()
    except ValueError:
        st.error(".env 数值配置无效，请检查 timeout / retries / context 限制。")
        return
    with st.sidebar:
        st.subheader("翻译设置")
        settings.model = st.text_input("Model", settings.model)
        settings.api_base_url = st.text_input("API base URL", settings.api_base_url)
        settings.target_language = st.text_input("Target language", settings.target_language)
        demo = st.checkbox("离线演示（原文回显，不调用模型）", value=False)
        use_cache = st.checkbox("使用本地已校验翻译缓存", value=True, disabled=demo)
        retry_label = st.selectbox(
            "断点续译策略",
            ("不续传", "仅重试失败", "重试失败和高风险", "全部重译"),
            disabled=demo,
        )
        retry_modes = {
            "不续传": "none",
            "仅重试失败": "failed",
            "重试失败和高风险": "risky",
            "全部重译": "all",
        }
        retry_mode = retry_modes[retry_label]
        st.caption(
            "API key 从本地 .env / 环境变量读取，不保存到结果。点击翻译或解释会将相关论文段落发送给所配置的 API 服务。"
        )
        imported = st.file_uploader("导入已有 PIR JSON", type=["json"])
        if imported and st.button("载入 PIR"):
            try:
                st.session_state.document = Document.model_validate_json(imported.getvalue())
            except ValueError:
                st.error("PIR JSON 格式或版本不正确。")
    query_id = st.query_params.get("document", "")
    if query_id and query_id != st.session_state.get("query_loaded"):
        if re.fullmatch(r"[0-9a-f]{20}", query_id):
            for candidate in (
                Path("output") / query_id / "document.json",
                Path("output/document.json"),
            ):
                if candidate.is_file():
                    try:
                        loaded = load_document(candidate)
                        if loaded.document_id == query_id:
                            st.session_state.document = loaded
                            st.session_state.query_loaded = query_id
                            break
                    except (OSError, ValueError):
                        st.warning("无法载入本地 PIR，请手动导入。")
        if "document" not in st.session_state:
            st.info("请在侧栏导入该 HTML 对应的 document.json。")
    translate_tab, detail_tab = st.tabs(["Translate", "Paragraph Detail"])
    with translate_tab:
        pdf = st.file_uploader("上传原生文本型学术 PDF", type=["pdf"])
        if st.button("Translate", type="primary", disabled=pdf is None):
            try:
                bar = st.progress(0.0, text="开始解析")

                def progress(done: int, total: int, message: str) -> None:
                    bar.progress(done / max(total, 1), text=message)

                with tempfile.TemporaryDirectory(prefix="apt-") as temp:
                    path = Path(temp) / "input.pdf"
                    path.write_bytes(pdf.getvalue())
                    if demo:
                        document = TranslationPipeline(DemoTranslator()).run(
                            path, target_language=settings.target_language, progress=progress
                        )
                    else:
                        previous = (
                            st.session_state.get("document") if retry_mode != "none" else None
                        )
                        cache = FileTranslationCache(settings.cache_dir) if use_cache else None
                        with OpenAICompatibleClient(settings) as client:
                            document = TranslationPipeline(
                                OpenAICompatibleTranslator(client, settings), cache=cache
                            ).run(
                                path,
                                target_language=settings.target_language,
                                progress=progress,
                                previous_document=previous,
                                retry_mode=retry_mode,
                            )
                    document.filename = Path(pdf.name).name
                persist(document)
                st.session_state.document = document
                st.query_params.clear()
                st.session_state.pop("selected_block", None)
            except (OSError, ValueError, TranslationError) as exc:
                st.error(str(exc))
        document = st.session_state.get("document")
        if document:
            if document.mode == "demo":
                st.warning("离线演示：原文回显，不是真实译文。")
            if document.status in ("partial", "failed"):
                st.warning("结果包含失败、校验风险或待 OCR 页面，请查看详情。")
            stats = document.processing
            st.caption(
                f"本次处理：API {stats.provider_calls} · 缓存 {stats.cache_hits} · "
                f"断点复用 {stats.resumed_blocks} · 失败 {stats.failed_blocks}"
            )
            left, right = st.columns(2)
            left.download_button(
                "下载 PIR JSON",
                document.model_dump_json(indent=2),
                file_name="document.json",
                mime="application/json",
            )
            right.download_button(
                "下载双语 HTML", render_html(document), file_name="document.html", mime="text/html"
            )
            components.html(render_html(document), height=750, scrolling=True)
    with detail_tab:
        document = st.session_state.get("document")
        if not document or not document.blocks:
            st.info("先翻译 PDF 或导入 PIR，再选择段落。")
            return
        ids = [b.block_id for b in document.blocks]
        requested = st.query_params.get("block", "")
        if st.session_state.get("selected_block") not in ids:
            st.session_state.selected_block = requested if requested in ids else ids[0]
        selected = st.selectbox(
            "段落",
            ids,
            format_func=lambda value: f"{value} · {document.block(value).text[:75]}",
            key="selected_block",
        )
        block = document.block(selected)
        left, right = st.columns(2)
        left.subheader("Original")
        left.text(block.text)
        right.subheader("Translation")
        right.text(block.translation or "尚未翻译")
        st.subheader("TransCheck")
        if block.check:
            st.json(block.check.model_dump())
        else:
            st.info(f"尚未校验；状态：{block.translation_status}")
        for warning in block.warnings:
            st.warning(warning)
        if st.button("Explain / 重新解释", disabled=demo or document.mode == "demo"):
            try:
                with (
                    st.spinner("正在结合摘要与相邻段落解释……"),
                    OpenAICompatibleClient(settings) as client,
                ):
                    PaperExplain(client, settings).explain(document, selected)
                persist(document)
                st.rerun()
            except (OSError, ValueError, TranslationError) as exc:
                st.error(str(exc))
        if block.explanation:
            st.subheader("Plain Explanation")
            st.text(block.explanation.plain_explanation)
            st.subheader("Role in Paper")
            st.text(block.explanation.role_in_paper)
            st.subheader("关键术语")
            for term in block.explanation.key_terms:
                st.text(f"{term.term} — {term.explanation}")
            st.caption(block.explanation.warning)
        else:
            st.caption("仅主动点击时调用 PaperExplain；不会自动解释全文。")


if __name__ == "__main__":
    main()
