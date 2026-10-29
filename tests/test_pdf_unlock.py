from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from mupdf_weakkey import _aes_encrypt, _find_key, _rng_bytes
from pdf_inspect import PdfInspection, format_inspection, identify_writer, inspect_pdf
import subprocess
import sys
from pdf_unlock import run


class PdfUnlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        pdf = fitz.open()
        pdf.new_page().insert_text((72, 72), "Unlock test")
        self.plain = self.root / "plain.pdf"
        self.locked = self.root / "locked.pdf"
        pdf.save(self.plain)
        pdf.save(
            self.locked,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="test1234",
            owner_pw="owner",
        )
        pdf.close()

    def test_plain_pdf(self) -> None:
        self.assertEqual(run([str(self.plain)]), 0)
        with fitz.open(self.root / "p-plain.pdf") as result:
            self.assertFalse(result.needs_pass)
            self.assertIn("Unlock test", result[0].get_text())

    def test_known_password(self) -> None:
        self.assertEqual(run([str(self.locked), "--password", "test1234"]), 0)
        with fitz.open(self.root / "p-locked.pdf") as result:
            self.assertFalse(result.needs_pass)
            self.assertIn("Unlock test", result[0].get_text())

    def test_wrong_password(self) -> None:
        self.assertEqual(
            run([str(self.locked), "--password", "wrong", "--engine", "password"]), 2
        )
        self.assertFalse((self.root / "p-locked.pdf").exists())

    def test_does_not_overwrite_by_default(self) -> None:
        self.assertEqual(run([str(self.plain)]), 0)
        self.assertEqual(run([str(self.plain)]), 2)
        self.assertEqual(run([str(self.plain), "--overwrite"]), 0)

    def test_inspect_encrypted_does_not_guess_producer(self) -> None:
        info = inspect_pdf(self.locked)
        self.assertTrue(info.encrypted)
        self.assertEqual(info.revision, 6)
        self.assertEqual(info.crypt_filter, "AESV3")
        self.assertEqual(info.candidates, ("mupdf", "foxit"))
        self.assertIsNone(info.producer)
        self.assertIn("unavailable", format_inspection(info))

    def test_inspect_does_not_create_output(self) -> None:
        self.assertEqual(run([str(self.locked), "--inspect"]), 0)
        self.assertFalse((self.root / "p-locked.pdf").exists())

    def test_engine_routing_does_not_equate_format_with_vendor(self) -> None:
        basic = dict(path=self.locked, encrypted=True, revision=6, crypt_filter="AESV3",
                     creator=None, version=None, metadata_available=True, parsed=True)
        self.assertEqual(PdfInspection(producer="Foxit PDF Reader", **basic).candidates,
                         ("foxit", "mupdf"))
        self.assertEqual(PdfInspection(producer="LibreOffice", **basic).candidates,
                         ("mupdf", "foxit"))
        self.assertEqual(PdfInspection(producer=None, **{**basic, "revision": 7,
                        "crypt_filter": "AESV4"}).candidates, ("foxit",))
        self.assertEqual(PdfInspection(producer=None, **{**basic, "revision": 4,
                        "crypt_filter": "AESV2"}).candidates, ())
        self.assertEqual(identify_writer({"producer": "PyMuPDF 1.26.7"}), "PyMuPDF")

    def test_original_cli_now_performs_inspection(self) -> None:
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / "pdf_print2pdf.py"),
                   str(self.locked), "--inspect"]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("R6, AESV3", result.stdout)
        self.assertFalse((self.root / "p-locked.pdf").exists())

    def test_weak_rng_seed_and_offset(self) -> None:
        # Self-contained /Perms fixture using the documented weak RNG.
        seed, offset = 241, 48
        stream = _rng_bytes(seed, 160)
        key = stream[offset : offset + 32]
        prefix = (-4 & 0xFFFFFFFF).to_bytes(4, "little") + b"\xff" * 4 + b"Tadb"
        encrypted = _aes_encrypt(key, bytes(16), prefix + b"test")
        fake_pdf = (
            b"/R 6 /AESV3 /P -4 /EncryptMetadata true /Perms<"
            + encrypted.hex().encode("ascii") + b">"
        )
        self.assertEqual(_find_key(fake_pdf), key)

    @unittest.skipUnless(
        getattr(fitz, "mupdf_version_tuple", (999,)) < (1, 28, 5),
        "MuPDF 1.28.5+ uses secure keys, not recoverable with the weak-key algorithm",
    )
    def test_vulnerable_mupdf_end_to_end(self) -> None:
        self.assertEqual(run([str(self.locked), "--engine", "mupdf"]), 0)
        with fitz.open(self.root / "p-locked.pdf") as result:
            self.assertFalse(result.needs_pass)
            self.assertIn("Unlock test", result[0].get_text())


if __name__ == "__main__":
    unittest.main()
