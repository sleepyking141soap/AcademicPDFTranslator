"""Small explicit heuristics, with confidence separate from extraction fidelity."""

import re

from academic_pdf_translator.pir.models import Block, BlockType

HEADINGS = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:abstract|introduction|background|related work|methods?|methodology|experiments?|results?|discussion|conclusions?|references|bibliography|acknowledg(?:e)?ments?|appendix)(?:\s.*)?$",
    re.I,
)


def classify(block: Block, body_size: float, page_height: float) -> BlockType:
    text = block.text.strip()
    sizes = [s.font_size for line in block.lines for s in line.spans]
    size = max(sizes, default=body_size)
    if re.fullmatch(r"\d+", text) and block.bbox[1] > page_height * 0.9:
        return BlockType.FOOTER
    if re.match(r"^(?:Fig(?:ure)?\.?\s*\d+|Table\s+(?:\d+|[IVXLCDM]+))\b", text, re.I):
        return BlockType.CAPTION
    if len(text) < 120 and HEADINGS.match(text):
        return BlockType.SECTION_TITLE
    if block.page == 1 and size >= body_size * 1.4 and block.bbox[1] < page_height * 0.3:
        return BlockType.TITLE
    if len(text) < 120 and size >= body_size * 1.12:
        return BlockType.SECTION_TITLE
    if len(text) < 120 and re.match(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+[A-Z]", text):
        return BlockType.SECTION_TITLE
    if text.startswith(("$$", "\\[")) or (
        "=" in text and len(text) < 120 and len(text.split()) < 14
    ):
        block.confidence = min(block.confidence, 0.65)
        block.warnings.append(
            "EquationHeuristic: retained without translation; inspect classification"
        )
        return BlockType.EQUATION
    return BlockType.PARAGRAPH
