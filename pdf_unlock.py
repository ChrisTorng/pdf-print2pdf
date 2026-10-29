#!/usr/bin/env python
"""Write unencrypted, normalized PDFs, recovering known weak-key formats."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pdf_inspect import PdfInspection, format_inspection, identify_writer, inspect_pdf

from pdf_print2pdf import (
    PrintJob,
    UserError,
    discover_sources,
    ensure_jobs_are_writable,
    make_jobs,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write unencrypted, normalized PDFs. Supports known passwords, "
            "weak MuPDF AES-256 keys, and the external V12 Foxit Rust CLI."
        )
    )
    parser.add_argument("source", type=Path, help="PDF file or folder")
    parser.add_argument("output", nargs="?", type=Path, help="Output PDF or folder")
    parser.add_argument("--password", help="Known PDF user/owner password")
    parser.add_argument(
        "--engine", choices=("auto", "password", "mupdf", "foxit"),
        default="auto", help="Key recovery strategy (default: auto)",
    )
    parser.add_argument(
        "--pocs", type=Path, help="Local clone of https://github.com/v12-security/pocs (Foxit only)",
    )
    parser.add_argument(
        "--foxit-exe", type=Path, help="Path to compiled foxit-decrypt.exe",
    )
    parser.add_argument(
        "--inspect", action="store_true",
        help="Only inspect encryption and available producer metadata; do not write PDF",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--recursive", action="store_true")
    return parser.parse_args(argv)


def find_pocs(provided: Path | None) -> Path:
    if provided is not None:
        return provided.expanduser().resolve()
    here = Path(__file__).resolve().parent
    candidates = (here / "pocs", here.parent / "pocs", Path.cwd() / "pocs")
    return next((path for path in candidates if path.is_dir()), candidates[0])


def run_foxit_cli(source: Path, destination: Path, args: argparse.Namespace) -> None:
    root = find_pocs(args.pocs)
    executable = (
        args.foxit_exe.expanduser().resolve() if args.foxit_exe
        else root / "pdf_decryptors" / "foxitpdf" / "target" / "release"
        / ("foxit-decrypt.exe" if os.name == "nt" else "foxit-decrypt")
    )
    if not executable.is_file():
        raise UserError(
            f"Foxit CLI not found: {executable}\n"
            "Build V12's foxit-decrypt using cargo build --release, or use --foxit-exe."
        )
    try:
        result = subprocess.run(
            [str(executable), str(source), str(destination)],
            text=True, capture_output=True, check=False,
        )
    except OSError as error:
        raise UserError(f"Cannot run Foxit CLI: {error}") from error
    if result.returncode != 0 or not destination.is_file():
        lines = (result.stderr or result.stdout).strip().splitlines()
        reason = lines[-1] if lines else f"exit code {result.returncode}"
        raise UserError(f"Foxit key recovery failed: {reason}")


def print_writer(document: object) -> None:
    """The recorded writer is not proof of which engine encrypted the file."""
    metadata = getattr(document, "metadata", None) or {}
    producer = metadata.get("producer")
    creator = metadata.get("creator")
    family = identify_writer(metadata)
    if producer:
        print(f"    Producer (metadata, after open): {producer}")
    if creator:
        print(f"    Creator (metadata, after open): {creator}")
    if family:
        print(f"    Recorded PDF writer family: {family} (not proof of encryption engine)")


def save_unencrypted(document: object, output: Path) -> None:
    import fitz

    # Stage next to the output so replacement is atomic on Windows too.
    fd, filename = tempfile.mkstemp(prefix=".pdf-unlock-", suffix=".pdf", dir=output.parent)
    os.close(fd)
    staged = Path(filename)
    try:
        document.save(
            staged, encryption=fitz.PDF_ENCRYPT_NONE, garbage=4,
            clean=True, deflate=True, deflate_images=True, deflate_fonts=True,
        )
        os.replace(staged, output)
    finally:
        staged.unlink(missing_ok=True)


def unlock_one(job: PrintJob, args: argparse.Namespace, info: PdfInspection) -> str:
    try:
        import fitz
    except ImportError as error:
        raise UserError(
            f"PyMuPDF missing from {sys.executable}; install using "
            f"\"{sys.executable}\" -m pip install -r requirements.txt"
        ) from error

    try:
        with fitz.open(job.source) as document:
            if not document.needs_pass:
                save_unencrypted(document, job.output)
                print_writer(document)
                return "not encrypted"
            if args.password is not None and document.authenticate(args.password):
                save_unencrypted(document, job.output)
                print_writer(document)
                return "known password"
    except fitz.FileDataError:
        # Foxit AESV4/R7 is not necessarily supported by installed PyMuPDF.
        if args.engine not in ("auto", "foxit"):
            raise

    if args.engine == "password":
        raise UserError(f"No valid PDF password provided: {job.source}")

    engines = info.candidates if args.engine == "auto" else (args.engine,)
    if not engines:
        raise UserError(
            f"No supported automatic recovery for {info.encryption_name}. "
            "Try a known password if available."
        )

    failures: list[str] = []
    for engine in engines:
        if engine == "mupdf":
            try:
                from mupdf_weakkey import NotVulnerableMuPDF, recover_pdf
            except ImportError as error:
                raise UserError(
                    "MuPDF recovery needs cryptography: "
                    f"\"{sys.executable}\" -m pip install -r requirements.txt"
                ) from error
            try:
                modified, access_password = recover_pdf(job.source)
                with fitz.open(stream=modified, filetype="pdf") as document:
                    if not document.authenticate(access_password):
                        raise NotVulnerableMuPDF("recovered key could not authenticate the PDF")
                    save_unencrypted(document, job.output)
                    print_writer(document)
                return "verified MuPDF-compatible weak RNG"
            except (NotVulnerableMuPDF, fitz.FileDataError) as error:
                failures.append(f"MuPDF: {error}")
        elif engine == "foxit":
            with tempfile.TemporaryDirectory(prefix="pdf-unlock-") as folder:
                recovered = Path(folder) / "recovered.pdf"
                try:
                    run_foxit_cli(job.source, recovered, args)
                    with fitz.open(recovered) as document:
                        if document.needs_pass:
                            raise UserError("Foxit CLI returned an encrypted PDF")
                        save_unencrypted(document, job.output)
                        print_writer(document)
                    return "verified Foxit/PDFium-compatible timestamp key"
                except (UserError, fitz.FileDataError) as error:
                    failures.append(f"Foxit: {error}")
        else:
            raise UserError(f"Unknown engine: {engine}")

    raise UserError("No applicable key could be recovered. " + " | ".join(failures))


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        sources = discover_sources(args.source, args.recursive)
        if not sources:
            print("No source PDFs found.")
            return 0
        if args.inspect:
            for index, source in enumerate(sources, 1):
                print(f"[{index}/{len(sources)}] {source}")
                print("    " + format_inspection(inspect_pdf(source, args.password)).replace("\n", "\n    "))
            return 0

        jobs = make_jobs(sources, args.output)
        ensure_jobs_are_writable(jobs, args.overwrite)
        for index, job in enumerate(jobs, 1):
            print(f"[{index}/{len(jobs)}] {job.source} -> {job.output}", flush=True)
            try:
                info = inspect_pdf(job.source, args.password)
                print("    " + format_inspection(info).replace("\n", "\n    "))
                method = unlock_one(job, args, info)
            except (OSError, ValueError, RuntimeError) as error:
                raise UserError(f"Failed to process {job.source}: {error}") from error
            print(f"    Method: {method}")
        print(f"Done. Created {len(jobs)} PDF file(s).")
        return 0
    except UserError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
