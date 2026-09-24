"""CLI for creating, validating, reviewing and scoring benchmark workspaces."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from academic_pdf_translator.pir.serializer import load_document

from .metrics import evaluate_workspace, save_report
from .models import DatasetSplit
from .storage import (
    add_document,
    init_workspace,
    load_annotation,
    load_workspace,
    resolve_workspace_path,
    validate_annotation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AcademicPDFTranslator benchmark tools")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create an empty local benchmark workspace")
    init.add_argument("workspace", type=Path)
    init.add_argument("--name", default="AcademicPDFTranslator calibration")
    init.add_argument("--description", default="")

    add = commands.add_parser("add", help="Add a PDF and create a draft annotation")
    add.add_argument("workspace", type=Path)
    add.add_argument("pdf", type=Path)
    add.add_argument("--pir", type=Path, help="Use an existing parse/translation PIR")
    add.add_argument(
        "--split", choices=[item.value for item in DatasetSplit], default="calibration"
    )
    add.add_argument("--domain", default="")
    add.add_argument("--notes", default="")

    validate = commands.add_parser("validate", help="Check annotation/PIR consistency")
    validate.add_argument("workspace", type=Path)

    evaluate = commands.add_parser("evaluate", help="Calculate reviewed benchmark metrics")
    evaluate.add_argument("workspace", type=Path)
    evaluate.add_argument("--output", type=Path)

    serve = commands.add_parser("serve", help="Open the local Streamlit annotation UI")
    serve.add_argument("workspace", type=Path)
    serve.add_argument("--port", type=int, default=8502)
    return parser


def _validate(workspace: Path) -> list[str]:
    root = workspace.resolve()
    manifest = load_workspace(root)
    errors: list[str] = []
    for entry in manifest.documents:
        try:
            document = load_document(resolve_workspace_path(root, entry.pir))
            annotation = load_annotation(resolve_workspace_path(root, entry.annotation))
            errors.extend(
                f"{entry.document_id}: {message}"
                for message in validate_annotation(document, annotation)
            )
            resolve_workspace_path(root, entry.source_pdf).stat()
        except (OSError, ValueError) as exc:
            errors.append(f"{entry.document_id}: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            init_workspace(args.workspace, args.name, args.description)
            print(args.workspace.resolve() / "manifest.json")
        elif args.command == "add":
            entry = add_document(
                args.workspace,
                args.pdf,
                pir_path=args.pir,
                split=DatasetSplit(args.split),
                domain=args.domain,
                notes=args.notes,
            )
            print(f"Added {entry.filename} as {entry.document_id}")
        elif args.command == "validate":
            errors = _validate(args.workspace)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print("Benchmark workspace is valid")
        elif args.command == "evaluate":
            summary = evaluate_workspace(args.workspace)
            output = args.output or args.workspace.resolve() / "reports" / "report.json"
            save_report(summary, output)
            print(summary.model_dump_json(indent=2))
            print(f"Report: {output.resolve()}")
            return 2 if summary.warnings else 0
        elif args.command == "serve":
            load_workspace(args.workspace)
            from academic_pdf_translator.evaluation import ui

            environment = os.environ.copy()
            environment["APT_BENCHMARK_WORKSPACE"] = str(args.workspace.resolve())
            return subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(Path(ui.__file__).resolve()),
                    "--server.address=127.0.0.1",
                    f"--server.port={args.port}",
                    "--server.headless=true",
                    "--browser.gatherUsageStats=false",
                ],
                env=environment,
            )
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
