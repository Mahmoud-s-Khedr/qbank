from io import BytesIO
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pymupdf
import pytest
from sqlalchemy.orm import Session

from qbank.services import sources
from qbank.services.errors import Invalid


@pytest.mark.parametrize("user_password", ["user-password", ""])
def test_encrypted_pdf_rejected_before_storage(
    monkeypatch: pytest.MonkeyPatch, user_password: str
) -> None:
    document: Any = pymupdf.open()  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
    document.new_page()
    encrypted: bytes = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,  # type: ignore[attr-defined]  # Missing from PyMuPDF stubs.
        owner_pw="owner-password",
        user_pw=user_password,
    )
    document.close()
    monkeypatch.setattr(sources, "get", lambda *_args: object())
    store = MagicMock()
    monkeypatch.setattr(sources, "get_store", lambda: store)
    with pytest.raises(Invalid, match="encrypted_pdf"):
        sources.upload(MagicMock(spec=Session), uuid4(), uuid4(), "Book", None, BytesIO(encrypted))
    store.put.assert_not_called()
