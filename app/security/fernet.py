"""Symmetric encryption for OAuth refresh tokens stored at rest.

Uses cryptography.Fernet (AES-128-CBC + HMAC-SHA256). Key is loaded from
settings.fernet_key. To rotate, generate a new key and re-encrypt all rows.
"""
from __future__ import annotations

from cryptography.fernet import Fernet


def generate_key() -> bytes:
    """Returns a base64-urlsafe 32-byte key suitable for Fernet."""
    return Fernet.generate_key()


class FernetCipher:
    def __init__(self, key: bytes | str) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str | None) -> bytes | None:
        if plaintext is None:
            return None
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes | None) -> str | None:
        if ciphertext is None:
            return None
        return self._fernet.decrypt(ciphertext).decode("utf-8")
