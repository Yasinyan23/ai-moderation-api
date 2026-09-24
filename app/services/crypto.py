"""Fernet symmetric encryption helpers for provider API keys."""
from cryptography.fernet import Fernet


def encrypt_key(raw_key: str, fernet_secret: str) -> str:
    """Encrypt a raw provider API key using Fernet."""
    f = Fernet(fernet_secret.encode())
    return f.encrypt(raw_key.encode()).decode()


def decrypt_key(encrypted_key: str, fernet_secret: str) -> str:
    """Decrypt a Fernet-encrypted provider API key."""
    f = Fernet(fernet_secret.encode())
    return f.decrypt(encrypted_key.encode()).decode()
