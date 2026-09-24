"""Bounded neighbor context shared by translation and PaperExplain."""

import json

from academic_pdf_translator.pir.models import BlockType, Document

from .base import TranslationContext


def context_for(
    document: Document, block_id: str, terminology: dict[str, str] | None = None
) -> TranslationContext:
    blocks = [
        b
        for b in document.blocks
        if b.block_type not in (BlockType.HEADER, BlockType.FOOTER, BlockType.REFERENCE)
    ]
    block = document.block(block_id)
    index = next((i for i, b in enumerate(blocks) if b.block_id == block_id), -1)
    previous = (
        next(
            (
                b.text
                for b in reversed(blocks[:index])
                if b.block_type == BlockType.PARAGRAPH and b.section == block.section
            ),
            "",
        )
        if index >= 0
        else ""
    )
    following = (
        next(
            (
                b.text
                for b in blocks[index + 1 :]
                if b.block_type == BlockType.PARAGRAPH and b.section == block.section
            ),
            "",
        )
        if index >= 0
        else ""
    )
    abstract = "\n".join(
        b.text
        for b in document.blocks
        if "abstract" in b.section.lower() and b.block_type == BlockType.PARAGRAPH
    )
    return TranslationContext(
        section=block.section,
        previous=previous,
        next=following,
        abstract=abstract,
        terminology=terminology or {},
    )


def bounded_context(
    context: TranslationContext, max_chars: int, *, include_abstract: bool = False
) -> dict[str, str]:
    """Distribute a total content-character budget; JSON framing is additional."""
    if max_chars < 0:
        raise ValueError("Context budget cannot be negative")
    fields = {
        "section": context.section,
        "terminology": json.dumps(context.terminology, ensure_ascii=False),
        "previous": context.previous,
        "next": context.next,
    }
    if include_abstract:
        fields["abstract"] = context.abstract
    budget = max_chars
    result: dict[str, str] = {}
    for index, (name, value) in enumerate(fields.items()):
        allocation = min(len(value), budget // (len(fields) - index))
        result[name] = (
            value[-allocation:] if name == "previous" and allocation else value[:allocation]
        )
        budget -= allocation
    return result
