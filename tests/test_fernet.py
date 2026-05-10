"""TDD for the Fernet wrapper used to encrypt OAuth refresh tokens at rest."""
from __future__ import annotations

import pytest

from app.security.fernet import FernetCipher, generate_key


def test_round_trip_encrypts_and_decrypts():
    key = generate_key()
    cipher = FernetCipher(key)
    plaintext = "ya29.a0Af-secret-google-token"
    encrypted = cipher.encrypt(plaintext)
    assert encrypted != plaintext.encode()
    assert cipher.decrypt(encrypted) == plaintext


def test_decrypt_with_wrong_key_raises():
    cipher_a = FernetCipher(generate_key())
    cipher_b = FernetCipher(generate_key())
    encrypted = cipher_a.encrypt("secret")
    with pytest.raises(Exception):
        cipher_b.decrypt(encrypted)


def test_encrypt_none_returns_none():
    cipher = FernetCipher(generate_key())
    assert cipher.encrypt(None) is None
    assert cipher.decrypt(None) is None
