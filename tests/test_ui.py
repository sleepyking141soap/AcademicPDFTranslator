from pathlib import Path

from streamlit.testing.v1 import AppTest

from academic_pdf_translator.evaluation.storage import add_document, init_workspace
from academic_pdf_translator.pipeline import TranslationPipeline
from academic_pdf_translator.translation.demo import DemoTranslator


def test_ui_starts_and_renders_pir(sample_pdf):
    ui = Path(__file__).parents[1] / "src/academic_pdf_translator/ui.py"
    app = AppTest.from_file(str(ui)).run(timeout=20)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Translate", "Paragraph Detail"]
    app.session_state.document = TranslationPipeline(DemoTranslator()).run(sample_pdf)
    app.run(timeout=20)
    assert not app.exception
    assert len(app.selectbox) == 2
    assert any(selectbox.label == "段落" for selectbox in app.selectbox)
    assert any("离线演示" in warning.value for warning in app.warning)


def test_annotation_ui_starts(monkeypatch, tmp_path, sample_pdf):
    workspace = tmp_path / "benchmark"
    init_workspace(workspace, "Calibration")
    add_document(workspace, sample_pdf)
    monkeypatch.setenv("APT_BENCHMARK_WORKSPACE", str(workspace))
    ui = Path(__file__).parents[1] / "src/academic_pdf_translator/evaluation/ui.py"
    app = AppTest.from_file(str(ui)).run(timeout=20)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "版面与阅读顺序",
        "保护项与翻译",
        "标注说明",
    ]
    assert any(selectbox.label == "页码" for selectbox in app.selectbox)
