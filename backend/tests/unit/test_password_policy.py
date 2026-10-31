import pytest
from pydantic import ValidationError

from qbank.schemas.auth import ChangePassword
from qbank.schemas.users import UserCreate
from qbank.security.passwords import common_passwords


def test_password_policy_for_create_and_change() -> None:
    expected_count = 1000
    current = "old"
    strong = "unusual safe passphrase!"
    assert len(common_passwords()) == expected_count
    for weak in ("short", "1234567890", "PASSWORD123"):
        with pytest.raises(ValidationError):
            UserCreate(email="teacher@example.org", name="Teacher", role="teacher", password=weak)
        with pytest.raises(ValidationError):
            ChangePassword(current_password=current, new_password=weak)
    assert ChangePassword(current_password=current, new_password=strong).new_password
