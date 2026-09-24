import pymupdf
import pytest

from academic_pdf_translator.parser.pdf_parser import NativePDFParser, PDFParseError
from academic_pdf_translator.pir.models import BlockType
from academic_pdf_translator.pir.serializer import load_document, save_document


def test_native_geometry_classes_and_order(sample_pdf, tmp_path):
    doc = NativePDFParser().parse(sample_pdf)
    assert len(doc.pages) == 2
    assert not any(p.requires_ocr for p in doc.pages)
    assert doc.pages[0].layout == "single_column"
    assert doc.pages[1].layout == "two_column"
    types = {b.block_type for b in doc.blocks}
    assert {
        BlockType.TITLE,
        BlockType.SECTION_TITLE,
        BlockType.PARAGRAPH,
        BlockType.CAPTION,
        BlockType.REFERENCE,
        BlockType.FOOTER,
    } <= types
    texts = [b.text for b in doc.pages[1].blocks]
    left_second = next(i for i, t in enumerate(texts) if t.startswith("A second experiment"))
    right_first = next(i for i, t in enumerate(texts) if t.startswith("The right column"))
    conclusion = next(i for i, t in enumerate(texts) if t == "4 Conclusion")
    assert left_second < right_first < conclusion
    for block in doc.blocks:
        assert block.lines and block.bbox[2] > block.bbox[0]
        assert block.lines[0].spans[0].font_name
        assert block.lines[0].spans[0].font_size > 0
        assert block.document_id == doc.document_id
    assert len({b.block_id for b in doc.blocks}) == len(doc.blocks)
    output = tmp_path / "document.json"
    save_document(doc, output)
    assert load_document(output) == doc
    assert NativePDFParser().parse(sample_pdf).document_id == doc.document_id

    legacy = doc.model_dump()
    legacy["schema_version"] = "0.1"
    legacy.pop("processing")
    for page in legacy["pages"]:
        for block in page["blocks"]:
            block.pop("translation_origin")
    migrated = type(doc).model_validate(legacy)
    assert migrated.schema_version == "0.1"
    assert migrated.processing.provider_calls == 0
    assert all(block.translation_origin == "none" for block in migrated.blocks)


def test_scanned_and_sparse_pages_marked(tmp_path):
    path = tmp_path / "scan.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.draw_rect(pymupdf.Rect(20, 20, 200, 200), fill=(0, 0, 0))
        page.insert_text((280, 780), "1")
        pdf.save(path)
    doc = NativePDFParser().parse(path)
    assert doc.pages[0].requires_ocr
    assert doc.warnings


def test_invalid_and_missing_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")
    with pytest.raises(PDFParseError):
        NativePDFParser().parse(path)
    with pytest.raises(PDFParseError):
        NativePDFParser().parse(tmp_path / "missing.pdf")


def test_image_only_and_encrypted_pdf(sample_pdf, tmp_path):
    scanned = tmp_path / "image_only.pdf"
    with pymupdf.open(sample_pdf) as source, pymupdf.open() as destination:
        image = source[0].get_pixmap().tobytes("png")
        page = destination.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=image)
        destination.save(scanned)
    doc = NativePDFParser().parse(scanned)
    assert doc.pages[0].requires_ocr and not doc.blocks

    encrypted = tmp_path / "encrypted.pdf"
    with pymupdf.open(sample_pdf) as source:
        source.save(
            encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="password"
        )
    with pytest.raises(PDFParseError, match="Encrypted"):
        NativePDFParser().parse(encrypted)
