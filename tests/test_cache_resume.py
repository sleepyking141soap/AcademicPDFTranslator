import json

import pytest

from academic_pdf_translator.pipeline import TranslationPipeline
from academic_pdf_translator.pir.models import CheckError
from academic_pdf_translator.translation.base import (
    BaseTranslator,
    TranslationContext,
    TranslationError,
    TranslationRequest,
)
from academic_pdf_translator.translation.cache import FileTranslationCache, request_key


class CountingTranslator(BaseTranslator):
    model_name = "test-model"
    cache_identity = "fixture-provider:test-model"

    def __init__(self, fail_text: str = ""):
        self.calls = 0
        self.fail_text = fail_text

    def translate(self, request):
        self.calls += 1
        if self.fail_text and self.fail_text in request.text:
            raise TranslationError("fixture interruption")
        return "测试译文：" + request.text


def test_cache_key_covers_material_inputs_without_credentials():
    base = TranslationRequest("text", "Chinese", TranslationContext(section="Methods"))
    assert request_key("provider:model", base) == request_key("provider:model", base)
    changed = TranslationRequest("text", "Chinese", TranslationContext(section="Results"))
    assert request_key("provider:model", base) != request_key("provider:model", changed)
    assert request_key("provider:model", base) != request_key("provider:other", base)


def test_file_cache_roundtrip_and_corrupt_entry_is_a_miss(tmp_path):
    cache = FileTranslationCache(tmp_path)
    request = TranslationRequest("text", "Chinese")
    assert cache.get("identity", request) is None
    cache.put("identity", request, "译文")
    assert cache.get("identity", request) == "译文"
    path = next(tmp_path.rglob("*.json"))
    path.write_text("not JSON", encoding="utf-8")
    assert cache.get("identity", request) is None
    path.write_text(
        json.dumps({"schema_version": 999, "raw_translation": "stale"}), encoding="utf-8"
    )
    assert cache.get("identity", request) is None


def test_second_run_uses_only_verified_cache_entries(sample_pdf, tmp_path):
    cache = FileTranslationCache(tmp_path / "cache")
    first_translator = CountingTranslator()
    first = TranslationPipeline(first_translator, cache=cache).run(sample_pdf)
    translated = [b for b in first.blocks if b.translation_status == "translated"]
    assert first_translator.calls == len(translated)
    assert first.processing.provider_calls == len(translated)
    assert list((tmp_path / "cache").rglob("*.json"))

    second_translator = CountingTranslator()
    second = TranslationPipeline(second_translator, cache=cache).run(sample_pdf)
    assert second_translator.calls == 0
    assert second.processing.provider_calls == 0
    assert second.processing.cache_hits == len(translated)
    assert all(
        b.translation_origin == "cache"
        for b in second.blocks
        if b.translation_status == "translated"
    )


def test_failed_verification_is_not_cached(sample_pdf, tmp_path):
    class Broken(CountingTranslator):
        def translate(self, request):
            self.calls += 1
            return "丢失所有占位符"

    cache_dir = tmp_path / "cache"
    document = TranslationPipeline(Broken(), cache=FileTranslationCache(cache_dir)).run(sample_pdf)
    assert document.status == "partial"
    risky = sum(b.check is not None and not b.check.passed for b in document.blocks)
    assert risky > 0

    # Blocks that genuinely had nothing protected may pass and be cached, but
    # every risky block must call the provider again on the next run.
    second = Broken()
    rerun = TranslationPipeline(second, cache=FileTranslationCache(cache_dir)).run(sample_pdf)
    assert second.calls == risky
    assert rerun.status == "partial"


def test_resume_failed_reuses_completed_blocks(sample_pdf):
    interrupted_translator = CountingTranslator("Domain alignment")
    interrupted = TranslationPipeline(interrupted_translator).run(sample_pdf)
    assert interrupted.status == "partial"
    assert sum(b.translation_status == "failed" for b in interrupted.blocks) == 1

    resumed_translator = CountingTranslator()
    resumed = TranslationPipeline(resumed_translator).run(
        sample_pdf, previous_document=interrupted, retry_mode="failed"
    )
    assert resumed.status == "completed"
    assert resumed_translator.calls == 1
    assert resumed.processing.provider_calls == 1
    assert resumed.processing.resumed_blocks > 0
    assert (
        sum(b.translation_origin == "resume" for b in resumed.blocks)
        == resumed.processing.resumed_blocks
    )


def test_retry_risky_only_retranslates_failed_check(sample_pdf):
    original = TranslationPipeline(CountingTranslator()).run(sample_pdf)
    risky = next(b for b in original.blocks if b.translation_status == "translated")
    risky.check.passed = False
    risky.check.risk_score = 0.5
    risky.check.errors.append(CheckError(type="FixtureRisk"))

    translator = CountingTranslator()
    rerun = TranslationPipeline(translator).run(
        sample_pdf, previous_document=original, retry_mode="risky"
    )
    assert translator.calls == 1
    assert rerun.block(risky.block_id).translation_origin == "provider"
    assert rerun.processing.resumed_blocks > 0


def test_retry_all_bypasses_previous_and_cache(sample_pdf, tmp_path):
    cache = FileTranslationCache(tmp_path / "cache")
    original = TranslationPipeline(CountingTranslator(), cache=cache).run(sample_pdf)
    translator = CountingTranslator()
    rerun = TranslationPipeline(translator, cache=cache).run(
        sample_pdf, previous_document=original, retry_mode="all"
    )
    assert translator.calls == original.processing.provider_calls
    assert rerun.processing.cache_hits == 0
    assert rerun.processing.resumed_blocks == 0


def test_resume_rejects_mismatched_settings_and_demo(sample_pdf):
    previous = TranslationPipeline(CountingTranslator()).run(sample_pdf)
    with pytest.raises(ValueError, match="target language"):
        TranslationPipeline(CountingTranslator()).run(
            sample_pdf,
            target_language="Japanese",
            previous_document=previous,
            retry_mode="failed",
        )

    other = CountingTranslator()
    other.model_name = "different-model"
    with pytest.raises(ValueError, match="model"):
        TranslationPipeline(other).run(sample_pdf, previous_document=previous, retry_mode="failed")

    with pytest.raises(ValueError, match="requires retry_mode"):
        TranslationPipeline(CountingTranslator()).run(sample_pdf, previous_document=previous)


def test_corrupt_completed_block_is_retranslated_even_in_failed_mode(sample_pdf):
    previous = TranslationPipeline(CountingTranslator()).run(sample_pdf)
    corrupt = next(
        block
        for block in previous.blocks
        if block.translation_status == "translated" and block.protected_items
    )
    corrupt.raw_translation = "占位符已损坏"
    translator = CountingTranslator()
    rerun = TranslationPipeline(translator).run(
        sample_pdf, previous_document=previous, retry_mode="failed"
    )
    assert translator.calls == 1
    assert rerun.block(corrupt.block_id).translation_origin == "provider"
