# Real-paper benchmark and annotation guide

The benchmark answers four separate questions:

1. Did the parser place existing blocks in the right reading order?
2. Did it assign useful block types?
3. Did AcademicGuard protect every required scientific token without excessive protection?
4. Did a particular model output preserve the paper's meaning?

These questions have different denominators. Unreviewed pages and blocks are excluded rather
than counted as failures or successes.

## Create a local workspace

```powershell
python benchmark.py init benchmark/workspace --name "Calibration set"

# Parse a PDF now and create a blank annotation draft.
python benchmark.py add benchmark/workspace papers/paper-01.pdf --domain "computer vision"

# Or associate an existing translated PIR with the PDF.
python benchmark.py add benchmark/workspace papers/paper-02.pdf `
  --pir output/paper-02/document.json --domain "semiconductor devices"

python benchmark.py validate benchmark/workspace
python benchmark.py serve benchmark/workspace
```

The UI listens on `127.0.0.1:8502` by default. It does not upload papers or annotations. The
workspace contains copied source PDFs, PIR predictions, annotations and reports. The default
location is ignored by Git.

Every annotation stores a fingerprint of block IDs, source text and geometry. Parser changes to
order or block type remain comparable. Changes to segmentation, text or coordinates invalidate
the annotation and require migration or review. Every reviewed translation also stores a hash;
replacing model output cannot silently reuse an earlier human verdict.

## Calibration batch

Start with five papers and about three representative pages from each paper. Include at least:

- one single-column paper;
- two different two-column publisher styles;
- pages containing figures, tables, equations and references;
- one page that the parser marks uncertain or `requires_ocr` if available.

Review about 30 translated paragraphs across abstracts, methods, results and limitations. Do not
translate whole papers manually. Correct or classify the passages that expose systematic errors.

## Annotation rules

### Reading order

First mark structured segmentation problems: missing text, over-splitting, over-merging, spurious
blocks, and paragraphs broken across pages. Then order blocks as a reader would consume the main
text. Keep captions near their figures or tables.
Headers and footers remain blocks, but their position should reflect their page location rather
than the scientific narrative. Mark a page reviewed only after checking every listed block.

The current metric is pairwise order accuracy. For every pair of blocks, it asks whether the
parser and reviewer place them in the same relative order. This is more informative than exact
page equality when only one local swap is wrong.

The segmentation issue-page rate is reported separately. The current tool records issue categories
and notes; it does not yet create replacement blocks for text that the parser completely missed.

### Block type

Use the existing PIR vocabulary: `title`, `section_title`, `paragraph`, `caption`, `table`,
`equation`, `reference`, `header`, `footer`, or `unknown`. Mark a type reviewed only when the
displayed block has been inspected.

### AcademicGuard

The UI pre-fills spans predicted by the current rules. Delete false positives, add missing items,
and keep exact `start`/`end` offsets. The saved value must equal the indicated substring. Precision,
recall and F1 use `(kind, value, start, end)` identities so repeated values remain separate.

### Translation

- `pass`: no substantive error.
- `minor_error`: local wording or fluency issue that does not change the main claim.
- `major_error`: incorrect condition, entity, relation, polarity, comparison, conclusion, or key
  terminology.
- `unusable`: substantial omission, corruption, or output that requires retranslation.

Apply all relevant error tags. A corrected translation is useful for later regression prompts but
is optional. Translation ratings require real translated PIR; parse-only and demo text should not
be rated.

## Produce a report

```powershell
python benchmark.py evaluate benchmark/workspace
```

The command writes `reports/report.json` and prints the same metrics. `null` means there are no
reviewed examples for that metric. `translation_acceptable_rate` counts `pass` and `minor_error`;
`translation_major_error_rate` counts `major_error` and `unusable`.

Metrics are descriptive for the labeled corpus. They are not calibrated probabilities and should
always be reported with the number of reviewed pages or blocks.
