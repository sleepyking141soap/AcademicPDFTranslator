"""Content-addressed local cache for verified provider translations."""

import hashlib
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from academic_pdf_translator.pir.serializer import atomic_write

from .base import TranslationRequest

CACHE_SCHEMA_VERSION = 1
PROMPT_VERSION = "translation-v1"


class CacheEntry(BaseModel):
    schema_version: int = CACHE_SCHEMA_VERSION
    raw_translation: str


class TranslationCache(Protocol):
    def get(self, identity: str, request: TranslationRequest) -> str | None: ...

    def put(self, identity: str, request: TranslationRequest, raw_translation: str) -> None: ...


def request_key(identity: str, request: TranslationRequest) -> str:
    """Hash every input that can materially alter a translation, excluding credentials."""
    payload = {
        "schema": CACHE_SCHEMA_VERSION,
        "prompt": PROMPT_VERSION,
        "identity": identity,
        "target_language": request.target_language,
        "text": request.text,
        "context": {
            "section": request.context.section,
            "previous": request.context.previous,
            "next": request.context.next,
            "terminology": request.context.terminology,
            "abstract": request.context.abstract,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class FileTranslationCache:
    """One JSON file per entry; corrupt entries degrade to cache misses."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _path(self, identity: str, request: TranslationRequest) -> Path:
        key = request_key(identity, request)
        return self.directory / key[:2] / f"{key}.json"

    def get(self, identity: str, request: TranslationRequest) -> str | None:
        if not identity:
            return None
        path = self._path(identity, request)
        try:
            entry = CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if entry.schema_version != CACHE_SCHEMA_VERSION or not entry.raw_translation.strip():
            return None
        return entry.raw_translation

    def put(self, identity: str, request: TranslationRequest, raw_translation: str) -> None:
        if not identity or not raw_translation.strip():
            return
        path = self._path(identity, request)
        entry = CacheEntry(raw_translation=raw_translation)
        atomic_write(path, entry.model_dump_json())
