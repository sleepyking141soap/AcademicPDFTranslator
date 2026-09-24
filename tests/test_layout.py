from academic_pdf_translator.parser.layout import reading_order
from academic_pdf_translator.pir.models import Block


def block(name, bbox):
    return Block(document_id="test", block_id=name, page=1, text="some paper text", bbox=bbox)


def test_insufficient_column_evidence_warns():
    blocks = [block("left", (50, 100, 250, 130)), block("right", (325, 100, 560, 130))]
    ordered, layout = reading_order(blocks, 612)
    assert layout == "uncertain"
    assert all(b.confidence < 0.7 and b.warnings for b in ordered)


def test_overlapping_spanning_block_warns():
    blocks = [
        block("left1", (50, 100, 250, 130)),
        block("left2", (50, 200, 250, 230)),
        block("right1", (325, 100, 560, 130)),
        block("right2", (325, 200, 560, 230)),
        block("span", (50, 110, 560, 140)),
    ]
    ordered, layout = reading_order(blocks, 612)
    assert layout == "uncertain"
    assert len(ordered) == len(blocks)
    assert len({b.block_id for b in ordered}) == len(blocks)
    assert next(b for b in ordered if b.block_id == "span").warnings


def test_footer_cannot_change_column_inference():
    blocks = [
        block("left1", (50, 100, 250, 130)),
        block("left2", (50, 200, 250, 230)),
        block("right1", (325, 100, 560, 130)),
        block("right2", (325, 200, 560, 230)),
        block("footer", (303, 760, 315, 780)),
    ]
    ordered, layout = reading_order(blocks, 612, 792)
    assert layout == "two_column"
    assert [b.block_id for b in ordered] == ["left1", "left2", "right1", "right2", "footer"]
