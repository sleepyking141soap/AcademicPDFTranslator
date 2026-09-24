"""TransCheck rules plus an extension protocol for future semantic verification."""

from collections import Counter
from typing import Protocol

from academic_pdf_translator.guard.patterns import scan
from academic_pdf_translator.pir.models import CheckError, CheckResult, ProtectedItem

from .rules import RULES, values


class SemanticVerifier(Protocol):
    def check(self, source: str, translation: str) -> CheckResult: ...


class TransCheck:
    def check(
        self,
        source: str,
        translation: str,
        protected_items: list[ProtectedItem] | None = None,
        guard_warnings: list[str] | None = None,
    ) -> CheckResult:
        """Check exact academic content, not meaning, fluency or factual truth."""
        errors: list[CheckError] = []
        for kind, pattern in RULES.items():
            expected, actual = values(pattern, source), values(pattern, translation)
            if expected != actual:
                errors.append(
                    CheckError(type=kind, source=str(dict(expected)), translation=str(dict(actual)))
                )
        if protected_items is not None:
            expected = Counter((item.kind, item.value) for item in protected_items)
            actual = Counter((kind, value) for kind, value, _, _ in scan(translation))
            if expected != actual:
                errors.append(
                    CheckError(
                        type="ProtectedTokenMismatch",
                        source=str(dict(expected)),
                        translation=str(dict(actual)),
                    )
                )
        for warning in guard_warnings or []:
            errors.append(CheckError(type="PlaceholderIntegrityError", message=warning))
        if source.strip() and not translation.strip():
            errors.append(CheckError(type="EmptyTranslation", source=source))
        return CheckResult(
            passed=not errors, risk_score=min(1.0, len(errors) * 0.25), errors=errors
        )
