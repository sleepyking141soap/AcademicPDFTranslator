# v0.2 alpha architecture

## Data boundaries

Parser backends produce a `Document` made of pages, ordered blocks, native lines and
font spans. Only the parser knows PyMuPDF. Downstream stages receive PIR; they never
reconstruct the paper from an unstructured full-document string. Document IDs derive
from SHA-256 of PDF bytes. New documents use PIR schema 0.2; schema 0.1 remains readable
so earlier results can be resumed after the new fields receive safe defaults.

The parser keeps native line boundaries and does not dehyphenate automatically.
Header/footer regions are excluded from column inference. Within a two-column region,
left precedes right. Spanning content separates vertical bands. Short prominent headings
outside the active opposite column can also separate bands. Overlap or insufficient
column evidence reduces confidence and attaches warnings. These are heuristics, not
trained probability estimates.

## Translation transaction

Each source block gets its own deterministic, collision-avoiding placeholder namespace.
Guard stores kind, exact value and original offsets for every protected occurrence.
Translation receives protected current text and separately bounded unprotected context.
Prompts instruct the provider to treat all paper content as data and output only the
current paragraph. Context is never interpreted as application instructions.

The raw provider output is retained. Restoration first audits token counts and then
performs one substitution pass. Missing items are not invented; duplicated placeholders
remain visible. TransCheck compares counted numeric and symbolic structures, quantities,
and the protection inventory. It also receives restoration warnings: even an output
containing the right literal number cannot pass if its required placeholder disappeared.

The pipeline has no dependency on an OpenAI SDK. `BaseTranslator` can use any provider.
`CompletionClient` abstracts the shared language-model call used by the OpenAI-compatible
adapter and PaperExplain. HTTP requests have timeouts, bounded transient retries, no
automatic redirects, and sanitized provider errors. API keys never enter PIR. A fatal
configuration/authentication response stops subsequent requests in that document.

Verified translations may be stored in a content-addressed local cache. Its key includes
the prompt/cache schema, endpoint fingerprint, model, target language, protected current
text, full neighbor context and terminology. Credentials are excluded. A cache candidate
is restored and checked again on every read; an invalid candidate becomes a provider miss
and is overwritten only if the fresh result passes. `retry all` bypasses the cache.

Resume re-parses the PDF and requires the same document hash, model, target language and
live mode. `failed` reuses completed translated blocks; `risky` additionally retranslates
blocks whose deterministic check failed; `all` requests every translatable block. Reused
blocks are checked again and record `translation_origin=resume`.

## Status semantics

- `pending`: parsed but no translation attempted.
- `translated`: provider returned output; check may pass or fail.
- `retained`: original content intentionally retained; not verified as translation.
- `failed`: no usable provider response.
- `demo`: explicitly labeled source echo; never verified.

Document `partial` means missing OCR content, uncertain reading order, failed calls or
failed deterministic checks. `completed` describes pipeline completion, not validated
meaning. Parse-only documents retain `parsed`. A page without any blocks still appears
in JSON/HTML with its OCR warning. Confidence gates green HTML badges independently
of the check's token consistency result.

`risk_score = min(1, 0.25 * error_count)` in the deterministic checker; failed calls and
demo output score 1. This is an inspection aid, not a calibrated probability. Unchanged
paragraph output requires review even if the scientific tokens match.

## Explanation and output

PaperExplain is never called by the translation pipeline. An explicit CLI/UI action
supplies abstract, section, previous/current/next and existing translation; structured
output is validated before writing it to the selected block. Original/translation fields
come from PIR, never from model-generated copies. Other paragraphs remain unexplained.

JSON uses UTF-8 and atomic file replacement. HTML escapes paper/model strings, has no
external assets and contains no credentials. The Explain link carries only document/block
IDs and opens the local UI. UI files are looked up only under fixed output locations with
a strict document ID pattern; arbitrary local paths cannot be passed through query strings.
Exporting a pair of JSON/HTML files is not an atomic multi-file transaction.

## Future seams, not implemented features

- `PaperParser`: alternative whole-document parsers such as MinerU or Docling.
- `PageEnricher`: selective OCR/vision processing of a native page.
- `PageFusion`: fuse alternative/native pages in a shared PDF coordinate system.
- `SemanticVerifier`: future meaning checks, separate from deterministic TransCheck.
- Versioned PIR: a future service and reader/mobile clients can consume the same contract.

No future extension is silently activated in this alpha. There is no server API, job queue, account
system, hosted deployment, vector database or PDF layout reconstruction.
