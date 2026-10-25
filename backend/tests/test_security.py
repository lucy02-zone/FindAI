from app.core.security import hash_password, verify_password


def test_password_hash_can_be_verified() -> None:
    password = "correct horse battery staple"

    hashed_password = hash_password(password)

    assert hashed_password.startswith("$argon2id$")
    assert verify_password(password, hashed_password) is True


def test_incorrect_password_does_not_verify() -> None:
    hashed_password = hash_password("correct horse battery staple")

    assert verify_password("incorrect password", hashed_password) is False


def test_hashing_same_password_uses_a_different_salt() -> None:
    password = "correct horse battery staple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_invalid_hash_is_rejected_without_raising() -> None:
    assert verify_password("any password", "not-a-valid-password-hash") is False
