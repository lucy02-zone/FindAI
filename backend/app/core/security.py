from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plaintext password using pwdlib's recommended Argon2 settings."""
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password, returning False for hashes this utility cannot parse."""
    try:
        return password_hash.verify(plain_password, hashed_password)
    except UnknownHashError:
        return False


def create_access_token(subject: str) -> str:
    """Create a signed access token for a stable user identifier."""
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": subject, "exp": expires_at},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
