"""Chat Completions transport with bounded retries and sanitized errors."""

import hashlib
import json
import logging
import time
from urllib.parse import urlsplit

import httpx

from academic_pdf_translator.config import Settings

from .base import BaseTranslator, CompletionClient, TranslationError, TranslationRequest
from .context import bounded_context
from .prompts import SYSTEM

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        if not settings.api_key:
            raise ValueError("Set APT_API_KEY (or OPENAI_API_KEY) in your environment or .env")
        if not settings.model.strip():
            raise ValueError("Set APT_MODEL or pass --model with a provider-supported model")
        parsed = urlsplit(settings.api_base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "API base URL must be an http(s) endpoint without credentials, query or fragment"
            )
        if settings.timeout <= 0 or not 0 <= settings.max_retries <= 5:
            raise ValueError("Timeout must be positive; max retries must be between 0 and 5")
        self.settings = settings
        self._client = httpx.Client(
            timeout=settings.timeout, transport=transport, follow_redirects=False
        )

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.settings.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._client.post(
                    self.settings.api_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.api_key}"},
                    json=payload,
                )
            except httpx.TransportError:
                if attempt == self.settings.max_retries:
                    raise TranslationError(
                        "API connection failed or timed out after bounded retries"
                    ) from None
                self._backoff(attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.settings.max_retries:
                    self._backoff(attempt)
                    continue
            if response.status_code != 200:
                # Never serialize response bodies: some gateways echo credentials/input.
                raise TranslationError(
                    f"API HTTP {response.status_code}; check provider settings and quota",
                    fatal=response.status_code in (400, 401, 403, 404),
                )
            try:
                choice = response.json()["choices"][0]
                content = choice["message"]["content"]
                finish = choice.get("finish_reason")
                if finish not in (None, "stop"):
                    raise TranslationError(
                        f"Incomplete API output (finish_reason={str(finish)[:30]})"
                    )
                if not isinstance(content, str) or not content.strip():
                    raise TranslationError("API returned empty or non-text content")
                return content.strip()
            except (KeyError, IndexError, TypeError, ValueError):
                raise TranslationError("Invalid Chat Completions response schema") from None
        raise TranslationError("API retries exhausted")

    @staticmethod
    def _backoff(attempt: int) -> None:
        logger.warning("Transient API failure; retry %d", attempt + 1)
        time.sleep(min(2**attempt, 8))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAICompatibleClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class OpenAICompatibleTranslator(BaseTranslator):
    def __init__(self, client: CompletionClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.model_name = settings.model
        endpoint_fingerprint = hashlib.sha256(
            settings.api_base_url.rstrip("/").encode("utf-8")
        ).hexdigest()[:16]
        self.cache_identity = f"chat-completions-v1:{endpoint_fingerprint}:{settings.model}"

    def translate(self, request: TranslationRequest) -> str:
        if len(request.text) > self.settings.max_current_chars:
            raise TranslationError(
                "Current protected block exceeds APT_MAX_CURRENT_CHARS; not silently truncated"
            )
        data = {
            "target_language": request.target_language,
            "context": bounded_context(request.context, self.settings.context_chars),
            "current_text": request.text,
        }
        return self.client.complete(SYSTEM, json.dumps(data, ensure_ascii=False))
