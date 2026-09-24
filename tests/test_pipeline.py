import json

import pytest

from academic_pdf_translator.config import Settings
from academic_pdf_translator.explain.paper_explain import PaperExplain
from academic_pdf_translator.export import export_document
from academic_pdf_translator.export.html_exporter import badge, render_html
from academic_pdf_translator.pipeline import TranslationPipeline
from academic_pdf_translator.pir.serializer import load_document
from academic_pdf_translator.translation.base import BaseTranslator, TranslationError
from academic_pdf_translator.translation.demo import DemoTranslator


class TestTranslator(BaseTranslator):
    __test__ = False

    def translate(self, request):
        # Contract fixture: changed prose plus exact opaque token preservation.
        return "测试译文：" + request.text


def test_pipeline_export_roundtrip(sample_pdf, tmp_path):
    events = []
    doc = TranslationPipeline(TestTranslator()).run(
        sample_pdf, progress=lambda *args: events.append(args)
    )
    assert events[-1][0] == events[-1][1] == len(doc.blocks)
    assert doc.status == "completed"
    assert all(b.check.passed for b in doc.blocks if b.translation_status == "translated")
    assert all(b.explanation is None for b in doc.blocks)
    paths = export_document(doc, tmp_path)
    assert load_document(paths[0]) == doc
    html = paths[1].read_text(encoding="utf-8")
    assert "✓ verified" in html and "Explain" in html
    assert "300 MHz" in html and "<AP" not in html


def test_demo_never_verified(sample_pdf):
    doc = TranslationPipeline(DemoTranslator()).run(sample_pdf)
    assert doc.mode == "demo"
    assert all(badge(b)[0] != "ok" for b in doc.blocks)


def test_placeholder_failure_recorded(sample_pdf):
    class Broken(BaseTranslator):
        def translate(self, request):
            return "译文丢失所有数字。"

    doc = TranslationPipeline(Broken()).run(sample_pdf)
    assert doc.status == "partial"
    assert any("MissingPlaceholder" in w for b in doc.blocks for w in b.warnings)
    assert any(b.check and not b.check.passed for b in doc.blocks)


def test_fatal_error_does_not_retry_every_paragraph(sample_pdf):
    class Broken(BaseTranslator):
        calls = 0

        def translate(self, request):
            self.calls += 1
            raise TranslationError("API HTTP 401", fatal=True)

    translator = Broken()
    doc = TranslationPipeline(translator).run(sample_pdf)
    assert translator.calls == 1
    assert doc.status == "partial"
    assert any(b.translation_status == "failed" for b in doc.blocks)


def test_html_escapes_all_paper_content(sample_pdf):
    doc = TranslationPipeline(TestTranslator()).run(sample_pdf)
    doc.title = "<script>alert('x')</script>"
    doc.blocks[0].translation = '<img src=x onerror="alert(1)">'
    html = render_html(doc)
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html


def test_paper_explain_is_explicit_and_has_context(sample_pdf):
    doc = TranslationPipeline(TestTranslator()).run(sample_pdf)
    block = next(b for b in doc.blocks if b.text.startswith("Domain alignment"))

    class FakeClient:
        calls = []

        def complete(self, system, user):
            self.calls.append(json.loads(user))
            return json.dumps(
                {
                    "plain_explanation": "分布接近不一定能区分样本。",
                    "role_in_paper": "指出已有方法的局限。",
                    "key_terms": [
                        {"term": "discriminability", "explanation": "区分不同类别的能力"}
                    ],
                }
            )

    client = FakeClient()
    assert not client.calls
    result = PaperExplain(client, Settings()).explain(doc, block.block_id)
    assert result.original == block.text and result.translation == block.translation
    assert client.calls[0]["context"]["abstract"]
    assert client.calls[0]["context"]["next"]
    assert sum(b.explanation is not None for b in doc.blocks) == 1


def test_invalid_explanation_is_not_saved(sample_pdf):
    doc = TranslationPipeline(TestTranslator()).run(sample_pdf)

    class BadClient:
        def complete(self, system, user):
            return '{"plain_explanation": 123}'

    with pytest.raises(TranslationError):
        PaperExplain(BadClient(), Settings()).explain(doc, doc.blocks[0].block_id)
    assert doc.blocks[0].explanation is None
