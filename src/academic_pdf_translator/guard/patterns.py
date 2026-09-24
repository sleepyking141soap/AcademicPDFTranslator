"""Ordered, non-overlapping token patterns. Longer structures take precedence."""

import re

# ASCII boundaries allow scientific tokens next to CJK translation text.
NUMBER = r"(?<![A-Za-z0-9_])[-+−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][-+−]?\d+|\s*[×x·]\s*10\s*\^\s*[-+−]?\d+|[×·]10[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+)?(?![0-9_])"
UNITS = r"(?:GHz|MHz|kHz|Hz|μm|µm|nm|mm|cm|km|mV|kV|dBm|dB|ns|ps|ms|°C|°F|mA|μA|mW|kW|kg|mg|MPa|kPa|Pa|V|A|W|K|s|m|g)"
UNIT = rf"(?<![A-Za-z_]){UNITS}(?![A-Za-z0-9_])"
CITATION = r"\[\s*\d+(?:\s*[,;–—-]\s*\d+)*\s*\]"
REFERENCE = r"(?<![A-Za-z])(?:Figs?\.?|Figures?|Tables?|Eqs?\.?|Equations?)\s*(?:\(\d+[a-z]?\)|\d+[a-z]?|[IVXLCDM]+)(?![A-Za-z0-9])"
TOKEN_PATTERN = r"<AP[0-9a-f]+_[A-Z]+_\d+>"

PATTERNS: list[tuple[str, str]] = [
    ("LITERAL", TOKEN_PATTERN),
    ("MATH", r"\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\]"),
    ("CIT", CITATION),
    ("REF", REFERENCE),
    ("PERCENT", rf"{NUMBER}\s*[%％]"),
    ("UNIT", UNIT),
    (
        "SYMBOL",
        r"(?<![A-Za-z0-9_])(?:[A-Za-z]+_[A-Za-z0-9]+|[A-Z][0-9]+|[A-Z]{2,}[A-Z0-9-]*)(?![A-Za-z0-9_])",
    ),
    ("VAR", r"[α-ωΑ-Ω](?:_[A-Za-z0-9]+)?|(?<![A-Za-z0-9_])[xyz](?![A-Za-z0-9_])"),
    ("NUM", NUMBER),
]
SCANNER = re.compile("|".join(f"(?P<{kind}>{pattern})" for kind, pattern in PATTERNS))
TOKEN_RE = re.compile(TOKEN_PATTERN)


def scan(text: str) -> list[tuple[str, str, int, int]]:
    """Extract disjoint protected spans using priority order."""
    return [(m.lastgroup or "", m.group(), m.start(), m.end()) for m in SCANNER.finditer(text)]
