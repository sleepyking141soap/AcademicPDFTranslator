# Contributing

Install Python 3.11+ and `pip install -e '.[dev]'`. Run `python -m pytest -q`,
`python -m ruff check .` and `python -m ruff format --check .` before submitting changes.
Tests must run without external model credentials. Keep synthetic examples small and
avoid committing private/copyrighted research papers or generated translations.

Bug reports for layout should include a shareable minimal PDF, the affected page/block,
expected reading order and parser version. Reports for Guard/TransCheck should contain
the exact source and output strings, including whitespace. Never include API keys.

Preserve PIR boundaries when adding a backend. New warning/failure cases should have a
regression test. Deterministic verification must stay separate from semantic verification.
Do not use a green badge to claim model quality or automatically hide corrupted output.
