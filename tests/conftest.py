"""Synthetic fixtures ensure tests never need credentials or copyrighted papers."""

from pathlib import Path

import pytest

from examples.create_sample import create_sample


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "paper.pdf"
    create_sample(path)
    return path
