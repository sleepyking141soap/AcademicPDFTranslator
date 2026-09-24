from collections import Counter

import pytest

from academic_pdf_translator.guard.academic_guard import AcademicGuard


@pytest.mark.parametrize(
    "value",
    [
        "0.873",
        "128",
        "3.2×10^-5",
        "5%",
        "98.2%",
        "300 MHz",
        "GHz",
        "kHz",
        "nm",
        "μm",
        "mm",
        "mV",
        "V",
        "dB",
        "dBm",
        "ns",
        "ps",
        "°C",
        "[1]",
        "[12]",
        "[23–26]",
        "[1, 2, 9]",
        "Fig. 3",
        "Figure 5",
        "Table II",
        "Table IV",
        "Eq. (4)",
        "ATE",
        "FPGA",
        "CPO",
        "S11",
        "S21",
        "AUROC",
        "F1",
        "x",
        "y",
        "L_cls",
        "α",
        "β",
        "σ",
        "$x^2 + y^2$",
        "\\(x=1\\)",
        "\\[L=2\\]",
        "$$x=3$$",
        "1.2e-5",
        "−0.5",
        "1,024",
        "3×10⁻⁵",
    ],
)
def test_roundtrip(value):
    guard = AcademicGuard()
    protected = guard.protect(f"The measurement is {value}.")
    assert protected.items
    assert "".join(i.value for i in protected.items).replace(" ", "") == value.replace(" ", "")
    assert guard.restore(protected.text, protected.items).text == f"The measurement is {value}."
    assert guard.restore(protected.text, protected.items).valid


def test_simulated_chinese_translation():
    guard = AcademicGuard()
    source = "The proposed method achieves a recall of 0.873 at 5% coverage [23]."
    protected = guard.protect(source)
    n, p, c = [i.placeholder for i in protected.items]
    result = guard.restore(f"该方法在{p}覆盖率下的召回率为{n}{c}。", protected.items)
    assert result.valid
    assert result.text == "该方法在5%覆盖率下的召回率为0.873[23]。"


def test_repeated_values_have_distinct_placeholders():
    guard = AcademicGuard()
    protected = guard.protect("128 and 128 and [12] and [12]")
    assert len({i.placeholder for i in protected.items}) == 4
    assert Counter(i.value for i in protected.items) == {"128": 2, "[12]": 2}
    assert guard.restore(protected.text, protected.items).valid


def test_missing_duplicate_unknown_and_mangled_are_visible():
    guard = AcademicGuard()
    protected = guard.protect("0.873 at 5%")
    token = protected.items[0].placeholder
    result = guard.restore(token + token + "<APabc_NUM_999>", protected.items)
    assert any("DuplicatePlaceholder" in w for w in result.warnings)
    assert any("MissingPlaceholder" in w for w in result.warnings)
    assert any("UnknownPlaceholder" in w for w in result.warnings)
    assert "0.873" not in result.text
    assert token in result.text
    assert not guard.restore(protected.text.replace("_NUM_", "_num_"), protected.items).valid


def test_literal_placeholder_and_formula_restore_once():
    guard = AcademicGuard()
    source = "An existing <APabc_NUM_001> with $x=5%$ and 128."
    protected = guard.protect(source)
    assert len(protected.items) == 3
    restored = guard.restore(protected.text, protected.items)
    assert restored.valid and restored.text == source


def test_no_tokens():
    guard = AcademicGuard()
    assert guard.protect("ordinary scientific prose").items == []
    assert guard.restore("普通文字", []).valid


@pytest.mark.parametrize("value", [".5", "−.25", ".05%", "-.5e-3"])
def test_leading_decimal_is_protected_as_a_whole(value):
    guard = AcademicGuard()
    protected = guard.protect(f"The value is {value}.")
    assert len(protected.items) == 1
    assert protected.items[0].value == value
    restored = guard.restore(protected.text, protected.items)
    assert restored.valid and restored.text == f"The value is {value}."
