# v0.2 alpha validation record

Date: 2026-09-22. Environment: Windows, isolated CPython 3.12.13 virtual environment.

## Automated checks

- `python -m pytest -q`: **119 passed**. No external model credentials required.
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed.
- `python -m pip check`: no broken requirements.
- `uv build --wheel --out-dir tmp/dist`: built a Python wheel; confirmed package modules,
  CLI entry point metadata, Streamlit UI module and full LICENSE are included.

The Windows system temporary directory contained an inaccessible historical pytest
directory. Tests used `TEMP` and `TMP` set to `tmp/test-runtime` under this repository,
as documented in README. No system permissions were changed.

## Core regressions covered

- Scientific values, units, citations, references, Greek variables and LaTeX round trips.
- Repeated values use distinct placeholders; missing, duplicated, unknown and malformed
  placeholders cannot silently pass verification.
- `.5`, negative leading decimals and scientific notation preserve the complete value;
  dropping the decimal point from `.5` to `5` is a NumberMismatch.
- Counts, percentages, unit changes and swapped number/unit pairings are checked.
- Native single/two-column reading order, spanning headings, ambiguous overlap, sparse
  text, image-only pages, corrupt/missing files and password-protected PDFs.
- Fatal provider errors stop subsequent requests; transient failures retry within bounds;
  empty, malformed and truncated responses fail explicitly.
- Real loopback HTTP service plus CLI subprocesses exercise Chat Completions request
  construction, PIR/HTML export, explicit PaperExplain and saved explanation output.
- PaperExplain context and JSON validation; model-supplied text cannot replace the
  original/translation fields stored in PIR.
- HTML escaping, demo labeling and Streamlit state rendering.
- Working-directory `.env` loading, environment precedence and invalid numeric settings.
- Content-addressed cache keys, corrupt/stale cache misses, verified-only writes, cache
  hits on repeat runs, failed/risky/all retry modes and resume configuration rejection.
- A completed PIR block with corrupted raw placeholder output is not reused, even under
  the cheaper failed-only resume policy; it is sent back to the provider.

The loopback service returns deterministic fixture text. It tests the HTTP/application
contract, **not translation or explanation quality**.

## PDF and command-line smoke test

`examples/sample_paper.pdf` is generated locally by `examples/create_sample.py` using
ReportLab. It contains two pages and 22 extracted blocks: one single-column page and
one two-column page, including headings, captions, scientific values and references.

- `python cli.py examples/sample_paper.pdf --demo`: completed, exported
  `output/document.json` and `output/document.html`.
- `python cli.py examples/sample_paper.pdf --parse-only --output output/parsed`: completed.
- Both PDF pages were rendered with Poppler and visually inspected for clipping,
  overlap and reading order. The sample is synthetic and contains no third-party paper.
- A discovered ordering bug placed the short Conclusion heading before right-column
  content. The parser now excludes page margins from column inference and recognizes
  prominent headings outside the opposite column's active vertical extent.

## Browser workflow

Started the real application with `python app.py`; local health endpoint returned
`200 ok`. Used headless Microsoft Edge through Playwright to perform:

1. Load Translate, confirm cache/resume controls, and enable clearly labeled offline demo mode.
2. Upload the sample PDF and click Translate.
3. Confirm downloadable JSON/HTML and render the 22-block result.
4. Open Paragraph Detail and inspect source, output and check details.
5. Confirm Explain is disabled for demo output.
6. Follow a document/block deep link into a fresh UI session and verify the selected
   paragraph is the requested Domain alignment paragraph.
7. Inspect standalone HTML at 1280px and 390px widths; no horizontal page overflow.
8. Confirm no browser page errors, and no green verified badges on demo output.

Desktop/mobile HTML and the paragraph detail view were also visually inspected.
Screenshots and the local browser harness remain in ignored `tmp/`, not the package.

## Not verified

- No real API key/model was configured. No external LLM translation, explanation
  quality, provider-specific behavior or live billing was tested.
- No broad real-paper corpus benchmark was run.
- GitHub Actions is configured for Windows/Linux and Python 3.11–3.14; those remote
  jobs have not been run. Local results above apply to Windows/Python 3.12.13.
- OCR, Vision, MinerU/Docling implementations, semantic verification, PDF layout
  rewriting and mobile clients are intentionally outside this alpha.
