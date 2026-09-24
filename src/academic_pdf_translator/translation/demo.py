"""Offline plumbing demonstration; deliberately never claims to translate."""

from .base import BaseTranslator, TranslationRequest


class DemoTranslator(BaseTranslator):
    is_demo = True
    model_name = "offline-demo-no-translation"
    cache_identity = ""

    def translate(self, request: TranslationRequest) -> str:
        return "【离线演示：以下为原文回显，并非译文】\n" + request.text
