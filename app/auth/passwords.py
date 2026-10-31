import bcrypt
from zxcvbn import zxcvbn

_MIN_ZXCVBN_SCORE = 3


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def check_password_strength(password: str) -> str | None:
    """Return why the password is too weak, or None if it's strong enough.

    zxcvbn can take hundreds of milliseconds on a long password, so call this off the event loop.
    """
    result = zxcvbn(password)
    if result["score"] >= _MIN_ZXCVBN_SCORE:
        return None
    warning: str | None = result["feedback"].get("warning")
    suggestions: list[str] = result["feedback"].get("suggestions", [])
    return warning or (suggestions[0] if suggestions else "Password is too weak")
