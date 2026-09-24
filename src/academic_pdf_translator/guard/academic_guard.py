"""Protect scientific tokens and fail visibly on corrupted placeholder output."""

import hashlib
from collections import Counter

from academic_pdf_translator.pir.models import ProtectedItem

from .patterns import TOKEN_RE, scan
from .placeholder import Protection, Restoration


class AcademicGuard:
    def protect(self, text: str) -> Protection:
        """Replace each occurrence with its own collision-free opaque token."""
        nonce = hashlib.sha256(text.encode()).hexdigest()[:12]
        while f"<AP{nonce}_" in text:
            nonce += "a"
        counts: Counter[str] = Counter()
        items: list[ProtectedItem] = []
        parts: list[str] = []
        cursor = 0
        for kind, value, start, end in scan(text):
            counts[kind] += 1
            placeholder = f"<AP{nonce}_{kind}_{counts[kind]:03d}>"
            items.append(
                ProtectedItem(placeholder=placeholder, kind=kind, value=value, start=start, end=end)
            )
            parts.extend((text[cursor:start], placeholder))
            cursor = end
        parts.append(text[cursor:])
        return Protection("".join(parts), items)

    def restore(self, text: str, items: list[ProtectedItem]) -> Restoration:
        """Restore exactly-once tokens in one pass; never invent missing values.

        Duplicated/unknown tokens remain visible. The caller must mark the result
        unverified whenever warnings are present.
        """
        mapping = {item.placeholder: item.value for item in items}
        counts = Counter(TOKEN_RE.findall(text))
        warnings: list[str] = []
        if len(mapping) != len(items):
            warnings.append("InvalidProtectionMap: duplicate placeholder identifiers")
        for token in mapping:
            if counts[token] == 0:
                warnings.append(f"MissingPlaceholder: {token}")
            elif counts[token] > 1:
                warnings.append(f"DuplicatePlaceholder: {token} ({counts[token]} occurrences)")
        for token in counts.keys() - mapping.keys():
            warnings.append(f"UnknownPlaceholder: {token}")
        restored = TOKEN_RE.sub(
            lambda m: (
                mapping[m.group()] if m.group() in mapping and counts[m.group()] == 1 else m.group()
            ),
            text,
        )
        return Restoration(restored, warnings)
