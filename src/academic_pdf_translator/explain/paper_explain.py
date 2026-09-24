"""Generate and validate an explanation only on explicit paragraph request."""

import json

from pydantic import BaseModel, Field, ValidationError

from academic_pdf_translator.config import Settings
from academic_pdf_translator.pir.models import Document, Explanation, TermExplanation
from academic_pdf_translator.translation.base import CompletionClient, TranslationError
from academic_pdf_translator.translation.context import bounded_context, context_for

from .prompts import SYSTEM


class ExplanationPayload(BaseModel):
    plain_explanation: str = Field(min_length=1)
    role_in_paper: str = Field(min_length=1)
    key_terms: list[TermExplanation] = Field(default_factory=list, max_length=30)


class PaperExplain:
    def __init__(self, client: CompletionClient, settings: Settings):
        self.client = client
        self.settings = settings

    def explain(self, document: Document, block_id: str) -> Explanation:
        block = document.block(block_id)
        if len(block.text) + len(block.translation) > self.settings.max_current_chars * 2:
            raise TranslationError("Paragraph too long for PaperExplain; no silent truncation")
        data = {
            "target_language": document.target_language,
            "context": bounded_context(
                context_for(document, block_id), self.settings.context_chars, include_abstract=True
            ),
            "current_text": block.text,
            "translation": block.translation,
            "translation_warnings": block.warnings[:10],
        }
        raw = self.client.complete(SYSTEM, json.dumps(data, ensure_ascii=False))
        # Tolerate a single enclosing fence; validate the actual JSON and its shape.
        if raw.startswith("```") and raw.endswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            payload = ExplanationPayload.model_validate_json(raw)
        except ValidationError:
            raise TranslationError(
                "PaperExplain returned invalid JSON; explanation was not saved"
            ) from None
        explanation = Explanation(
            original=block.text, translation=block.translation, **payload.model_dump()
        )
        block.explanation = explanation
        return explanation
