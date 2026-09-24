"""UTF-8 PIR storage with atomic replacement."""

import os
import tempfile
from pathlib import Path

from .models import Document


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_document(document: Document, path: str | Path) -> Path:
    path = Path(path)
    atomic_write(path, document.model_dump_json(indent=2))
    return path


def load_document(path: str | Path) -> Document:
    return Document.model_validate_json(Path(path).read_text(encoding="utf-8"))
