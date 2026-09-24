"""Stable request contracts for translators and completion providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol


class TranslationError(RuntimeError):
    def __init__(self, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


@dataclass
class TranslationContext:
    section: str = ""
    previous: str = ""
    next: str = ""
    terminology: dict[str, str] = field(default_factory=dict)
    abstract: str = ""


@dataclass
class TranslationRequest:
    text: str
    target_language: str
    context: TranslationContext = field(default_factory=TranslationContext)


class CompletionClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class BaseTranslator(ABC):
    is_demo: bool = False
    model_name: str = "custom"
    cache_identity: str = ""

    @abstractmethod
    def translate(self, request: TranslationRequest) -> str:
        """Return only the translation of request.text, retaining all placeholders."""
