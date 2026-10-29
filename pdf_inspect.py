"""Inspect PDF encryption characteristics without relying on editable producer names.

A PDF may encrypt its Info strings and XMP data, so before unlocking the
producer is often unknowable. This module reports evidence, not certainty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfInspection:
    path: Path
    encrypted: bool | None
    revision: int | None
    crypt_filter: str | None
    producer: str | None
    creator: str | None
    version: str | None
    metadata_available: bool
    parsed: bool
    note: str = ""

    @property
    def encryption_name(self) -> str:
        if self.encrypted is False:
            return "none"
        parts = []
        if self.revision is not None:
            parts.append(f"R{self.revision}")
        if self.crypt_filter is not None:
            parts.append(self.crypt_filter)
        return ", ".join(parts) or "unknown"

    @property
    def candidates(self) -> tuple[str, ...]:
        """Compatible recovery algorithms; not claims of the originating app."""
        if self.encrypted is False:
            return ()
        if self.revision == 7 and self.crypt_filter == "AESV4":
            return ("foxit",)
        if self.revision == 6 and self.crypt_filter == "AESV3":
            signature = " ".join((self.producer or "", self.creator or "")).lower()
            if "foxit" in signature or "pdfium" in signature:
                return ("foxit", "mupdf")
            return ("mupdf", "foxit")
        return ()


def _get_field(raw: bytes, key: bytes) -> int | None:
    match = re.search(rb"/" + key + rb"\s+(\d+)(?=\s|/|>|$)", raw)
    return int(match.group(1)) if match else None


def _crypt_method(raw: bytes) -> str | None:
    # A crypt-filter method is not an application signature.
    match = re.search(rb"/CFM\s*/(AESV[34])\b", raw)
    return match.group(1).decode("ascii") if match else None


def inspect_pdf(path: Path, password: str | None = None) -> PdfInspection:
    import fitz

    path = path.expanduser().resolve()
    try:
        with fitz.open(path) as doc:
            if not doc.is_pdf:
                raise ValueError("not a PDF")
            encrypted = bool(doc.needs_pass or doc.is_encrypted)
            if encrypted and password is not None and doc.needs_pass:
                doc.authenticate(password)
            trailer = doc.pdf_trailer().encode("latin-1", errors="replace")
            if not encrypted:
                metadata = doc.metadata or {}
                return PdfInspection(
                    path, False, None, None,
                    metadata.get("producer") or None,
                    metadata.get("creator") or None,
                    metadata.get("format") or None, True, True,
                )
            metadata = doc.metadata or {}
            return PdfInspection(
                path, True, _get_field(trailer, b"R"), _crypt_method(trailer),
                metadata.get("producer") or None,
                metadata.get("creator") or None,
                metadata.get("format") or None,
                bool(metadata.get("producer") or metadata.get("creator")), True,
            )
    except (fitz.FileDataError, fitz.EmptyFileError, fitz.FileNotFoundError) as error:
        # Some readers cannot load revision-7 PDFs. Raw tokens are unverified.
        raw = path.read_bytes()
        if not raw.startswith(b"%PDF-"):
            raise ValueError("not a PDF") from error
        return PdfInspection(
            path, None, _get_field(raw, b"R"), _crypt_method(raw),
            None, None, raw[1:8].decode("latin-1", errors="replace"),
            False, False,
            "Reader could not parse the PDF; revision/method are unverified raw-token hints",
        )


def identify_writer(metadata: dict[str, str] | None) -> str | None:
    """Classify the recorded writer, not necessarily the encrypting engine."""
    meta = metadata or {}
    text = " ".join((meta.get("producer") or "", meta.get("creator") or "")).lower()
    for term, writer in (
        ("pymupdf", "PyMuPDF"),
        ("mupdf", "MuPDF"),
        ("foxit", "Foxit"),
        ("pdfium", "PDFium"),
        ("itext", "iText"),
        ("openpdf", "OpenPDF"),
        ("adobe", "Adobe"),
        ("ghostscript", "Ghostscript"),
        ("microsoft", "Microsoft"),
    ):
        if term in text:
            return writer
    return None


def format_inspection(info: PdfInspection) -> str:
    if info.encrypted is False:
        encryption = "Not encrypted"
    elif info.encrypted is None:
        encryption = f"Uncertain ({info.encryption_name})"
    else:
        encryption = info.encryption_name

    lines = [f"Encryption: {encryption}"]
    if info.producer:
        lines.append(f"Producer (metadata): {info.producer}")
    if info.creator:
        lines.append(f"Creator (metadata): {info.creator}")
    if info.encrypted is not False and not info.metadata_available:
        lines.append("Producer/Creator: unavailable until decrypted or absent")
    lines.append("Candidate methods: " + (", ".join(info.candidates) or "none"))
    if info.note:
        lines.append("Note: " + info.note)
    return "\n".join(lines)
