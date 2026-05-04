#!/usr/bin/env python
"""Re-create PDF files by rewriting them with PyMuPDF."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PrintJob:
    source: Path
    output: Path


class UserError(Exception):
    """An expected input or environment problem."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-create PDF files by rewriting them to new PDF files. "
            "A source can be one PDF file or one folder containing PDF files."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source PDF file or source folder.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help=(
            "Optional output PDF file or output folder. For multiple source PDFs, "
            "this must be a folder."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Read PDFs from the source folder recursively.",
    )
    return parser.parse_args(argv)


def is_pdf(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() == ".pdf"


def is_self_output_pdf(path: Path) -> bool:
    return path.name.casefold().startswith("p-") and path.suffix.casefold() == ".pdf"


def discover_sources(source: Path, recursive: bool) -> list[Path]:
    source = source.expanduser().resolve()

    if source.is_file():
        if source.suffix.casefold() != ".pdf":
            raise UserError(f"Source file is not a PDF: {source}")
        return [source]

    if source.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdfs = [
            path.resolve()
            for path in source.glob(pattern)
            if is_pdf(path) and not is_self_output_pdf(path)
        ]
        return sorted(pdfs, key=lambda path: str(path).casefold())

    raise UserError(f"Source path does not exist: {source}")


def output_kind(output: Path | None) -> str:
    if output is None:
        return "default"
    if output.exists() and output.is_dir():
        return "folder"
    if output.suffix.casefold() == ".pdf":
        return "file"
    return "folder"


def make_jobs(sources: list[Path], output: Path | None) -> list[PrintJob]:
    if not sources:
        return []

    kind = output_kind(output)

    if kind == "file":
        if len(sources) != 1:
            raise UserError("An output PDF filename can only be used with one source PDF.")
        assert output is not None
        return [PrintJob(sources[0], output.expanduser().resolve())]

    if kind == "folder":
        assert output is not None
        output_folder = output.expanduser().resolve()
        return [
            PrintJob(source, output_folder / f"p-{source.name}")
            for source in sources
        ]

    return [
        PrintJob(source, source.parent / f"p-{source.name}")
        for source in sources
    ]


def ensure_jobs_are_writable(jobs: list[PrintJob], overwrite: bool) -> None:
    seen_outputs: dict[Path, Path] = {}

    for job in jobs:
        normalized_output = job.output.resolve()
        previous_source = seen_outputs.get(normalized_output)
        if previous_source is not None:
            raise UserError(
                "Multiple source PDFs would write to the same output file:\n"
                f"  {previous_source}\n"
                f"  {job.source}\n"
                f"Output: {job.output}"
            )
        seen_outputs[normalized_output] = job.source

        job.output.parent.mkdir(parents=True, exist_ok=True)

        if normalized_output == job.source.resolve():
            raise UserError(f"Output would overwrite the source PDF: {job.output}")

        if job.output.exists() and not overwrite:
            raise UserError(
                f"Output already exists: {job.output}\n"
                "Use --overwrite if replacing existing files is intended."
            )


def rewrite_pdf(job: PrintJob) -> None:
    try:
        import fitz
    except ImportError as error:
        raise UserError(
            "PyMuPDF is not installed for the Python executable running this script.\n"
            f"Python executable: {sys.executable}\n"
            f"Install with: \"{sys.executable}\" -m pip install -r requirements.txt"
        ) from error

    with fitz.open(job.source) as document:
        document.save(
            job.output,
            garbage=4,
            clean=True,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
        )


def run(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        sources = discover_sources(args.source, args.recursive)
        if not sources:
            print("No source PDFs found.", file=sys.stderr)
            return 0

        jobs = make_jobs(sources, args.output)
        ensure_jobs_are_writable(jobs, args.overwrite)

        for index, job in enumerate(jobs, start=1):
            print(f"[{index}/{len(jobs)}] {job.source} -> {job.output}")
            rewrite_pdf(job)

        print(f"Done. Created {len(jobs)} PDF file(s).")
        return 0
    except UserError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
