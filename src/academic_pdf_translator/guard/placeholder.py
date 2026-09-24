"""Protection and restoration outcomes."""

from dataclasses import dataclass, field

from academic_pdf_translator.pir.models import ProtectedItem


@dataclass
class Protection:
    text: str
    items: list[ProtectedItem] = field(default_factory=list)


@dataclass
class Restoration:
    text: str
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.warnings
