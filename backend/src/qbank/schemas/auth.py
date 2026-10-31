from pydantic import BaseModel, field_validator

from qbank.security.passwords import validate_password


class Login(BaseModel):
    email: str
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    _validate_password = field_validator("new_password")(validate_password)
