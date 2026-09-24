"""Orchestrate parser -> guard -> contextual translation -> deterministic checks."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from academic_pdf_translator.guard.academic_guard import AcademicGuard
from academic_pdf_translator.parser.base import PaperParser
from academic_pdf_translator.parser.pdf_parser import NativePDFParser
from academic_pdf_translator.pir.models import (
    Block,
    BlockType,
    CheckError,
    CheckResult,
    Document,
)
from academic_pdf_translator.translation.base import (
    BaseTranslator,
    TranslationError,
    TranslationRequest,
)
from academic_pdf_translator.translation.cache import TranslationCache
from academic_pdf_translator.translation.context import context_for
from academic_pdf_translator.verification.transcheck import TransCheck

logger = logging.getLogger(__name__)
Progress = Callable[[int, int, str], None]
RetryMode = Literal["none", "failed", "risky", "all"]
RETAIN = {
    BlockType.REFERENCE,
    BlockType.EQUATION,
    BlockType.TABLE,
    BlockType.HEADER,
    BlockType.FOOTER,
}


class TranslationPipeline:
    def __init__(
        self,
        translator: BaseTranslator,
        *,
        parser: PaperParser | None = None,
        terminology: dict[str, str] | None = None,
        cache: TranslationCache | None = None,
    ):
        self.translator = translator
        self.parser = parser or NativePDFParser()
        self.terminology = terminology or {}
        self.cache = cache
        self.guard = AcademicGuard()
        self.checker = TransCheck()

    def run(
        self,
        pdf: str | Path,
        *,
        target_language: str = "Simplified Chinese",
        progress: Progress | None = None,
        previous_document: Document | None = None,
        retry_mode: RetryMode = "none",
    ) -> Document:
        if retry_mode not in ("none", "failed", "risky", "all"):
            raise ValueError(f"Unsupported retry mode: {retry_mode}")
        if previous_document is not None and retry_mode == "none":
            raise ValueError("A previous PIR requires retry_mode failed, risky, or all")
        if previous_document is not None and self.translator.is_demo:
            raise ValueError("Resume is unavailable in demo mode")
        if progress:
            progress(0, 1, "Parsing native PDF")
        document = self.parser.parse(pdf)
        document.target_language = target_language
        document.mode = "demo" if self.translator.is_demo else "live"
        document.model = self.translator.model_name
        previous = self._validate_previous(document, previous_document, target_language)
        if self.translator.is_demo:
            document.warnings.append(
                "DEMO ONLY: source echo, no LLM translation or semantic validation."
            )
        blocks = document.blocks
        fatal_error = ""
        for index, block in enumerate(blocks):
            protection = self.guard.protect(block.text)
            block.protected_items, block.protected_text = protection.items, protection.text
            old = previous.get(block.block_id)
            if block.block_type in RETAIN:
                block.translation = block.text
                block.translation_status = "retained"
                block.translation_origin = "retained"
                block.warnings.append(
                    f"RetainedOriginal: {block.block_type}; not translated or verified"
                )
                document.processing.retained_blocks += 1
            elif old is not None and self._can_resume(old, retry_mode):
                self._resume_block(block, old)
                document.processing.resumed_blocks += 1
            else:
                try:
                    if fatal_error:
                        raise TranslationError(f"Skipped after fatal provider error: {fatal_error}")
                    request = TranslationRequest(
                        protection.text,
                        target_language,
                        context_for(document, block.block_id, self.terminology),
                    )
                    cache_allowed = (
                        self.cache is not None
                        and bool(self.translator.cache_identity)
                        and retry_mode != "all"
                    )
                    cached = (
                        self.cache.get(self.translator.cache_identity, request)
                        if cache_allowed
                        else None
                    )
                    initial_warnings = list(block.warnings)
                    if cached is not None and self._apply_raw(block, cached, from_demo=False):
                        block.translation_origin = "cache"
                        document.processing.cache_hits += 1
                    else:
                        # A stale/corrupt cache entry is a miss, not a user-visible result.
                        block.warnings = initial_warnings
                        block.raw_translation = ""
                        block.translation = ""
                        block.check = None
                        block.translation_status = "pending"
                        if not self.translator.is_demo:
                            document.processing.provider_calls += 1
                        block.raw_translation = self.translator.translate(request)
                        self._apply_raw(
                            block, block.raw_translation, from_demo=self.translator.is_demo
                        )
                        block.translation_origin = "demo" if self.translator.is_demo else "provider"
                        if (
                            cache_allowed
                            and block.check is not None
                            and block.check.passed
                            and not block.warnings
                        ):
                            self.cache.put(
                                self.translator.cache_identity, request, block.raw_translation
                            )
                except TranslationError as exc:
                    if exc.fatal:
                        fatal_error = str(exc)
                    block.translation_status = "failed"
                    block.translation_origin = "provider"
                    block.warnings.append(str(exc))
                    block.check = CheckResult(
                        passed=False,
                        risk_score=1,
                        errors=[CheckError(type="TranslationFailed", message=str(exc))],
                    )
                    logger.warning("Translation failed for %s: %s", block.block_id, exc)
            if progress:
                progress(index + 1, len(blocks), block.block_id)
        document.processing.failed_blocks = sum(
            block.translation_status == "failed" for block in blocks
        )
        failed = document.processing.failed_blocks > 0
        risky = any(b.check and not b.check.passed for b in blocks) and not self.translator.is_demo
        incomplete = any(p.requires_ocr or p.layout == "uncertain" for p in document.pages)
        document.status = "partial" if failed or risky or incomplete else "completed"
        if not blocks:
            document.status = "failed"
        return document

    def _validate_previous(
        self,
        document: Document,
        previous_document: Document | None,
        target_language: str,
    ) -> dict[str, Block]:
        if previous_document is None:
            return {}
        if previous_document.document_id != document.document_id:
            raise ValueError("Resume PIR belongs to a different PDF")
        if previous_document.target_language != target_language:
            raise ValueError("Resume PIR target language does not match this run")
        if previous_document.model != self.translator.model_name:
            raise ValueError("Resume PIR model does not match this run")
        if previous_document.mode != "live":
            raise ValueError("Only a live-translation PIR can be resumed")
        current_text = {block.block_id: block.text for block in document.blocks}
        return {
            block.block_id: block
            for block in previous_document.blocks
            if current_text.get(block.block_id) == block.text
        }

    def _can_resume(self, block: Block, retry_mode: RetryMode) -> bool:
        if retry_mode == "all" or block.translation_status != "translated":
            return False
        restoration = self.guard.restore(block.raw_translation, block.protected_items)
        if not restoration.valid or restoration.text != block.translation:
            return False
        if retry_mode == "risky" and (block.check is None or not block.check.passed):
            return False
        return retry_mode in ("failed", "risky")

    def _resume_block(self, block: Block, old: Block) -> None:
        """Copy a completed block after rechecking it against the current source."""
        block.protected_items = old.protected_items
        block.protected_text = old.protected_text
        self._apply_raw(block, old.raw_translation, from_demo=False)
        block.translation_origin = "resume"
        block.explanation = old.explanation

    def _apply_raw(self, block: Block, raw: str, *, from_demo: bool) -> bool:
        """Restore and check one result. Return whether a cached result is reusable."""
        restoration = self.guard.restore(raw, block.protected_items)
        check = self.checker.check(
            block.text, restoration.text, block.protected_items, restoration.warnings
        )
        warnings = list(restoration.warnings)
        if from_demo:
            check = CheckResult(
                passed=False,
                risk_score=1,
                errors=[
                    CheckError(
                        type="DemoNotTranslation",
                        message="Offline echo is not a translation",
                    )
                ],
            )
        elif (
            block.text.strip() == restoration.text.strip()
            and block.block_type == BlockType.PARAGRAPH
        ):
            warnings.append(
                "UnchangedTranslation: paragraph is identical to the original; review required"
            )
            check.errors.append(CheckError(type="UnchangedTranslation"))
            check.passed = False
            check.risk_score = max(0.5, check.risk_score)
        block.raw_translation = raw
        block.translation = restoration.text
        block.warnings.extend(warnings)
        block.check = check
        block.translation_status = "demo" if from_demo else "translated"
        return check.passed and not warnings
