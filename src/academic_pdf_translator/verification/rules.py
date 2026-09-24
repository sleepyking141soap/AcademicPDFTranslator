"""Counted token comparisons: multiplicity matters, order may change in translation."""

import re
from collections import Counter

from academic_pdf_translator.guard.patterns import CITATION, NUMBER, REFERENCE, UNIT, UNITS

RULES = {
    "NumberMismatch": NUMBER,
    "PercentageMismatch": rf"{NUMBER}\s*[%％]",
    "UnitMismatch": UNIT,
    "CitationMismatch": CITATION,
    "FigureTableReferenceMismatch": REFERENCE,
    "QuantityMismatch": rf"{NUMBER}\s*{UNITS}(?![A-Za-z0-9_])",
}


def values(pattern: str, text: str) -> Counter[str]:
    return Counter(re.sub(r"\s+", "", m.group()) for m in re.finditer(pattern, text))
