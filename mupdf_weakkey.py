"""Recover AES-256 PDFs written with MuPDF's pre-1.28.5 weak RNG.

Independent implementation of the key-generation weakness described by V12:
https://v12.sh/blog/the-case-of-the-9bit-aes-key

The recovered file key is rewrapped under a temporary known password so
PyMuPDF can save an ordinary, unencrypted PDF. No intermediate PDF is saved.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_MULTIPLIER = 0x5DEECE66D
_MASK = (1 << 48) - 1
_TEMP_PASSWORD = b"pdf-print2pdf-weakkey"


class NotVulnerableMuPDF(ValueError):
    """The input doesn't match supported vulnerable MuPDF PDF encryption."""


def _aes_encrypt(key: bytes, iv: bytes, raw: bytes) -> bytes:
    encryption = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryption.update(raw) + encryption.finalize()


def _aes_decrypt_block(key: bytes, raw: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return cipher.update(raw) + cipher.finalize()


def _rng_bytes(seed: int, length: int) -> bytes:
    current = (seed << 16) | 0x330E
    output = bytearray(length)
    for position in range(length):
        current = (current * _MULTIPLIER + 11) & _MASK
        output[position] = (current >> 17) & 255
    return bytes(output)


def _find_key(raw_pdf: bytes) -> bytes:
    if not re.search(rb"/R\s+6\b", raw_pdf) or b"/AESV3" not in raw_pdf:
        raise NotVulnerableMuPDF("not a supported revision-6 AESV3 PDF")

    permissions = re.search(rb"/P\s+(-?\d+)\b", raw_pdf)
    encrypted = re.search(rb"/Perms\s*<([\da-fA-F]{32})>", raw_pdf)
    if permissions is None or encrypted is None:
        raise NotVulnerableMuPDF("unsupported /P or /Perms PDF encoding")

    flags = (int(permissions.group(1)) & 0xFFFFFFFF).to_bytes(4, "little")
    encrypts_metadata = re.search(rb"/EncryptMetadata\s+false\b", raw_pdf) is None
    prefix = flags + bytes([255] * 4) + (b"T" if encrypts_metadata else b"F") + b"adb"
    encrypted_block = bytes.fromhex(encrypted.group(1).decode("ascii"))

    match = None
    for seed in range(512):
        # Some builds reuse the RNG across saves. Search extra stream offsets.
        # Validate candidates using the known /Perms plaintext prefix.
        generated = _rng_bytes(seed, 1056)
        for skip in range(1025):
            candidate = generated[skip : skip + 32]
            if _aes_decrypt_block(candidate, encrypted_block)[:12] == prefix:
                if match is not None:
                    raise NotVulnerableMuPDF("ambiguous weak-key candidates")
                match = candidate
    if match is None:
        raise NotVulnerableMuPDF("no matching weak MuPDF key")
    return match


def _rev6_hash(password: bytes, salt: bytes) -> bytes:
    digest = hashlib.sha256(password + salt).digest()
    count = 0
    last = 0
    while count < 64 or count < last + 32:
        payload = (password + digest) * 64
        encrypted = _aes_encrypt(digest[:16], digest[16:32], payload)
        digest_type = (hashlib.sha256, hashlib.sha384, hashlib.sha512)[sum(encrypted[:16]) % 3]
        digest = digest_type(encrypted).digest()
        last = encrypted[-1]
        count += 1
    return digest[:32]


def recover_pdf(raw_path: Path) -> bytes:
    """Return a still-encrypted PDF whose password is exposed by temp_password().

    Output is for transient in-memory use only. Only the final PyMuPDF output
    should be written to disk.
    """
    pdf = raw_path.read_bytes()
    key = _find_key(pdf)
    validation_salt = b"P2PDFVAL"
    wrapping_salt = b"P2PDFKEY"
    user_entry = _rev6_hash(_TEMP_PASSWORD, validation_salt) + validation_salt + wrapping_salt
    wrap_key = _rev6_hash(_TEMP_PASSWORD, wrapping_salt)
    wrapped_key = _aes_encrypt(wrap_key, bytes(16), key)

    new_pdf, count_u = re.subn(
        rb"/U\s*<[\da-fA-F]{96}>",
        b"/U<" + user_entry.hex().encode("ascii") + b">", pdf, count=1,
    )
    new_pdf, count_ue = re.subn(
        rb"/UE\s*<[\da-fA-F]{64}>",
        b"/UE<" + wrapped_key.hex().encode("ascii") + b">", new_pdf, count=1,
    )
    if (count_u, count_ue) != (1, 1):
        raise NotVulnerableMuPDF("unsupported PDF encryption dictionary layout")
    return new_pdf


def temp_password() -> str:
    return _TEMP_PASSWORD.decode("ascii")
