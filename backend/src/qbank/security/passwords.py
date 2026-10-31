"""Password policy shared by API and administrative CLI."""

from functools import lru_cache
from importlib.resources import files

MIN_PASSWORD_LENGTH = 10


@lru_cache
def common_passwords() -> frozenset[str]:
    data = files("qbank.security").joinpath("common_passwords.txt").read_text(encoding="utf-8")
    return frozenset(line.strip().casefold() for line in data.splitlines())


def validate_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError("Password must contain at least 10 characters")
    if value.casefold() in common_passwords():
        raise ValueError("Password is too common")
    return value
