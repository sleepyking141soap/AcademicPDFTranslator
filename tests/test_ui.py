from pathlib import Path

from streamlit.testing.v1 import AppTest

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
