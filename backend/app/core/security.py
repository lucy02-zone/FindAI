from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

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
