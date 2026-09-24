import pytest

from academic_pdf_translator.guard.academic_guard import AcademicGuard
from academic_pdf_translator.verification.transcheck import TransCheck


@pytest.mark.parametrize(
    ("source", "translation", "error"),
    [
        ("0.873", "0.837", "NumberMismatch"),
        ("13.2%", "31.2%", "PercentageMismatch"),
        ("300 MHz", "300 GHz", "UnitMismatch"),
        ("[12]", "[13]", "CitationMismatch"),
        ("[23–26]", "", "CitationMismatch"),
        ("Fig. 3", "Fig. 5", "FigureTableReferenceMismatch"),
        ("Table IV", "Table VI", "FigureTableReferenceMismatch"),
        ("128 128", "128", "NumberMismatch"),
        ("300 MHz and 500 GHz", "300 GHz and 500 MHz", "QuantityMismatch"),
        ("5% and 10", "5 and 10%", "PercentageMismatch"),
        ("value", "", "EmptyTranslation"),
    ],
)
def test_mismatches(source, translation, error):
    result = TransCheck().check(source, translation)
    assert not result.passed and result.risk_score > 0
    assert error in [e.type for e in result.errors]


def test_correct_chinese_translation_passes():
    source = "The FPGA operates at 300 MHz with 0.873 recall [12]."
    translation = "FPGA在300 MHz运行，召回率为0.873[12]。"
    items = AcademicGuard().protect(source).items
    assert TransCheck().check(source, translation, items).passed


def test_symbols_and_formula_changed():
    source = "S21 and $x=1$ and α"
    result = TransCheck().check(
        source, "S11 and $x=2$ and β", AcademicGuard().protect(source).items
    )
    assert "ProtectedTokenMismatch" in [e.type for e in result.errors]


def test_guard_warning_cannot_pass_even_with_matching_text():
    assert not TransCheck().check("128", "128", guard_warnings=["MissingPlaceholder"]).passed


def test_reordered_tokens_pass_and_substrings_do_not():
    guard = AcademicGuard()
    assert TransCheck().check("5% 128", "128 5%", guard.protect("5% 128").items).passed
    assert not TransCheck().check("S21", "AS21Z", guard.protect("S21").items).passed


@pytest.mark.parametrize("value", ["0.873", ".5", "-.25", "300 MHz", "[12]", "5%"])
def test_identical_values_pass(value):
    assert TransCheck().check(value, value, AcademicGuard().protect(value).items).passed


def test_dropped_decimal_point_is_a_number_mismatch():
    result = TransCheck().check(".5", "5")
    assert not result.passed
    assert "NumberMismatch" in [error.type for error in result.errors]
