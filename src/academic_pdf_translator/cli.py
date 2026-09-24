"""Command line translation, parse-only inspection and explicit paragraph explanation."""

import argparse
import json
import logging
from pathlib import Path

from academic_pdf_translator.config import Settings
from academic_pdf_translator.explain.paper_explain import PaperExplain
from academic_pdf_translator.export import export_document
from academic_pdf_translator.parser.pdf_parser import NativePDFParser
from academic_pdf_translator.pipeline import TranslationPipeline
from academic_pdf_translator.pir.serializer import load_document
from academic_pdf_translator.translation.base import TranslationError
from academic_pdf_translator.translation.cache import FileTranslationCache
from academic_pdf_translator.translation.demo import DemoTranslator
from academic_pdf_translator.translation.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleTranslator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Native academic PDF translation with AcademicGuard and TransCheck"
    )
    parser.add_argument("pdf", nargs="?", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--model")
    parser.add_argument("--api-base-url")
    parser.add_argument("--target-language")
    parser.add_argument(
        "--glossary", type=Path, help="JSON object mapping source terms to preferred translations"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--demo", action="store_true", help="Offline source echo; NOT real translation"
    )
    mode.add_argument("--parse-only", action="store_true")
    parser.add_argument("--pir", type=Path, help="Existing PIR JSON for --explain")
    parser.add_argument("--explain", metavar="BLOCK_ID")
    parser.add_argument("--resume", type=Path, help="Previous PIR JSON for interrupted work")
    parser.add_argument(
        "--retry",
        choices=("failed", "risky", "all"),
        help="With --resume: retry failed only (default), failed/risky, or every block",
    )
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write cache")
    parser.add_argument("--cache-dir", type=Path, help="Override APT_CACHE_DIR")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )
    # httpx INFO logs contain URLs; don't log provider URLs/queries by default.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.explain and (
        not args.pir or args.pdf or args.demo or args.parse_only or args.resume or args.retry
    ):
        parser.error("Use --pir FILE --explain BLOCK_ID, without a PDF or demo/parse-only mode")
    if not args.explain and (not args.pdf or args.pir):
        parser.error("Provide a PDF, or use --pir FILE --explain BLOCK_ID")
    if args.retry and not args.resume:
        parser.error("--retry requires --resume")
    if args.resume and (args.demo or args.parse_only):
        parser.error("--resume requires live translation mode")
    try:
        settings = Settings.from_env()
        for name in ("model", "api_base_url", "target_language"):
            if getattr(args, name) is not None:
                setattr(settings, name, getattr(args, name))
        if args.cache_dir is not None:
            settings.cache_dir = args.cache_dir
        terminology = json.loads(args.glossary.read_text(encoding="utf-8")) if args.glossary else {}
        if not isinstance(terminology, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in terminology.items()
        ):
            raise ValueError("Glossary must be a JSON object of string-to-string mappings")
        if args.explain:
            document = load_document(args.pir)
            with OpenAICompatibleClient(settings) as client:
                PaperExplain(client, settings).explain(document, args.explain)
        elif args.parse_only:
            document = NativePDFParser().parse(args.pdf)
            document.target_language = settings.target_language
        else:

            def progress(done: int, total: int, message: str) -> None:
                print(f"[{done}/{total}] {message}", flush=True)

            if args.demo:
                document = TranslationPipeline(DemoTranslator(), terminology=terminology).run(
                    args.pdf, target_language=settings.target_language, progress=progress
                )
            else:
                previous = load_document(args.resume) if args.resume else None
                retry_mode = args.retry or ("failed" if previous else "none")
                cache = None if args.no_cache else FileTranslationCache(settings.cache_dir)
                with OpenAICompatibleClient(settings) as client:
                    document = TranslationPipeline(
                        OpenAICompatibleTranslator(client, settings),
                        terminology=terminology,
                        cache=cache,
                    ).run(
                        args.pdf,
                        target_language=settings.target_language,
                        progress=progress,
                        previous_document=previous,
                        retry_mode=retry_mode,
                    )
        paths = export_document(document, args.output)
        for path in paths:
            print(path.resolve())
        print(f"Status: {document.status}; mode: {document.mode}")
        stats = document.processing
        print(
            "Work: "
            f"provider={stats.provider_calls}, cache={stats.cache_hits}, "
            f"resumed={stats.resumed_blocks}, failed={stats.failed_blocks}"
        )
        return 2 if document.status in ("partial", "failed") else 0
    except (OSError, ValueError, KeyError, TranslationError) as exc:
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
