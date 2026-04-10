"""ConexReport - Autenticação (stdlib only, sem dependências externas)."""

import hashlib
import secrets


# ---------------------------------------------------------------------------
# Password hashing — PBKDF2-SHA256 (OWASP recommended)
# ---------------------------------------------------------------------------

_ITERATIONS = 260_000  # OWASP 2024 minimum for PBKDF2-SHA256


def hash_password(password: str) -> str:
    """Retorna string no formato 'pbkdf2_sha256$iterations$salt_hex$hash_hex'."""
    salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica senha contra hash armazenado."""
    try:
        _, iterations_str, salt_hex, expected_hex = stored_hash.split("$")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(dk.hex(), expected_hex)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

SESSION_TTL_HOURS = 15  # Duração de uma sessão


def create_session_token() -> str:
    """Gera token de sessão com 384 bits de entropia."""
    return secrets.token_urlsafe(48)
