"""Conservative two-column ordering with spanning headings as vertical separators."""

from collections import Counter

from academic_pdf_translator.pir.models import Block


def reading_order(
    blocks: list[Block], width: float, height: float | None = None
) -> tuple[list[Block], str]:
    """Read left column then right within bands separated by spanning blocks."""
    if height is not None:
        top = [b for b in blocks if b.bbox[3] < height * 0.05]
        bottom = [b for b in blocks if b.bbox[1] > height * 0.94]
        body = [b for b in blocks if b not in top and b not in bottom]
        ordered, layout = reading_order(body, width)
        return sorted(top, key=lambda b: b.bbox[1]) + ordered + sorted(
            bottom, key=lambda b: b.bbox[1]
        ), layout
    middle, tolerance = width / 2, width * 0.015

    separators: set[str] = set()

    def side(b: Block) -> str:
        if b.block_id in separators:
            return "span"
        if b.bbox[2] <= middle + tolerance and b.bbox[0] < middle - tolerance:
            return "left"
        if b.bbox[0] >= middle - tolerance:
            return "right"
        return "span"

    left = [b for b in blocks if side(b) == "left"]
    right = [b for b in blocks if side(b) == "right"]
    # Both columns must share a meaningful vertical band.
    paired = any(
        min(a.bbox[3], b.bbox[3]) >= max(a.bbox[1], b.bbox[1]) for a in left for b in right
    )
    if not (len(left) >= 2 and len(right) >= 2 and paired):
        ordered = sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
        if paired:
            for block in ordered:
                block.confidence = min(block.confidence, 0.55)
                block.warnings.append(
                    "ReadingOrderUncertain: insufficient evidence for two columns"
                )
            return ordered, "uncertain"
        return ordered, "single_column"

    # Short full-width section headings often have a left-column-sized text bbox.
    # Treat prominent headings outside the opposite column's vertical extent as
    # separators, while headings within an active column remain in that column.
    fonts: Counter[float] = Counter()
    for block in blocks:
        for line in block.lines:
            for span in line.spans:
                fonts[round(span.font_size, 1)] += len(span.text)
    body_size = fonts.most_common(1)[0][0] if fonts else 10.0
    right_top = min(b.bbox[1] for b in right)
    right_bottom = max(b.bbox[3] for b in right)
    for block in left:
        size = max((s.font_size for line in block.lines for s in line.spans), default=body_size)
        if (
            size >= body_size * 1.12
            and len(block.text) < 120
            and (block.bbox[3] < right_top or block.bbox[1] > right_bottom)
        ):
            separators.add(block.block_id)
    spans = sorted((b for b in blocks if side(b) == "span"), key=lambda b: b.bbox[1])
    left = [b for b in left if b.block_id not in separators]
    remaining = left + right
    result: list[Block] = []
    uncertain = False
    for span in spans:
        before = [b for b in remaining if b.bbox[1] < span.bbox[1]]
        result.extend(sorted(before, key=lambda b: (side(b) == "right", b.bbox[1], b.bbox[0])))
        remaining = [b for b in remaining if b not in before]
        # Overlapping full-width material makes this band ambiguous.
        overlap = [
            b
            for b in left + right
            if min(b.bbox[3], span.bbox[3]) - max(b.bbox[1], span.bbox[1]) > 3
        ]
        if overlap:
            uncertain = True
            for block in [span, *overlap]:
                block.confidence = min(block.confidence, 0.5)
                block.warnings.append(
                    "ReadingOrderUncertain: spanning block overlaps column content"
                )
        result.append(span)
    result.extend(sorted(remaining, key=lambda b: (side(b) == "right", b.bbox[1], b.bbox[0])))
    return result, "uncertain" if uncertain else "two_column"
