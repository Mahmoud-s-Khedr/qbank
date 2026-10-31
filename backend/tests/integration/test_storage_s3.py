from uuid import uuid4

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from qbank.storage import S3Store


@pytest.mark.integration
def test_s3_round_trip() -> None:
    store = S3Store()
    try:
        store.ensure_bucket()
    except (BotoCoreError, ClientError, OSError):
        pytest.skip("MinIO unavailable")
    key = f"tests/{uuid4()}/file"
    try:
        store.put_bytes(key, b"data", "application/octet-stream")
        assert store.exists(key)
        assert store.get_bytes(key) == b"data"
        store.delete_prefix(key)
        assert not store.exists(key)
    finally:
        store.delete(key)
