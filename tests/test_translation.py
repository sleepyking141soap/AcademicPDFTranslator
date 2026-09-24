import json

import httpx
import pytest

from academic_pdf_translator.config import Settings
from academic_pdf_translator.translation.base import (
    TranslationContext,
    TranslationError,
    TranslationRequest,
)
from academic_pdf_translator.translation.context import bounded_context
from academic_pdf_translator.translation.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleTranslator,
)


def response(content="译文", finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def test_custom_endpoint_and_context():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=response())

    settings = Settings(
        model="custom-model",
        api_key="test-secret",
        api_base_url="https://provider.example/v1/",
        context_chars=100,
    )
    with OpenAICompatibleClient(settings, transport=httpx.MockTransport(handler)) as client:
        translator = OpenAICompatibleTranslator(client, settings)
        assert (
            translator.translate(
                TranslationRequest(
                    "CURRENT", "Chinese", TranslationContext(previous="p" * 500, next="n" * 500)
                )
            )
            == "译文"
        )
    assert str(seen[0].url) == "https://provider.example/v1/chat/completions"
    payload = json.loads(seen[0].content)
    current = json.loads(payload["messages"][1]["content"])
    assert current["current_text"] == "CURRENT"
    assert sum(map(len, current["context"].values())) <= 100
    assert "test-secret" not in repr(settings)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        response(""),
        response(None),
        response("partial", "length"),
        response("refused", "content_filter"),
    ],
)
def test_bad_output_fails(payload):
    with OpenAICompatibleClient(
        Settings(model="test", api_key="test"),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(TranslationError):
            client.complete("system", "data")


def test_retry_and_redaction(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "academic_pdf_translator.translation.openai_compatible.time.sleep", lambda _: None
    )

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(503, text="secret-api-key")
            if len(calls) == 1
            else httpx.Response(200, json=response())
        )

    with OpenAICompatibleClient(
        Settings(model="test", api_key="secret-api-key"), transport=httpx.MockTransport(handler)
    ) as client:
        assert client.complete("s", "u") == "译文"
    assert len(calls) == 2
    with OpenAICompatibleClient(
        Settings(model="test", api_key="test"),
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="secret-api-key")),
    ) as client:
        with pytest.raises(TranslationError) as error:
            client.complete("s", "u")
        assert error.value.fatal
        assert "secret-api-key" not in str(error.value)


def test_character_limits_and_config():
    assert sum(map(len, bounded_context(TranslationContext(previous="x" * 100), 5).values())) <= 5
    with pytest.raises(ValueError):
        OpenAICompatibleClient(Settings(model="test"))
    translator = OpenAICompatibleTranslator(None, Settings(max_current_chars=3))
    with pytest.raises(TranslationError, match="not silently truncated"):
        translator.translate(TranslationRequest("too long", "Chinese"))
