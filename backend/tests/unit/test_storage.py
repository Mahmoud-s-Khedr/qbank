from io import BytesIO
from pathlib import Path

import pytest

from qbank.storage import LocalStore


def test_local_storage_round_trip_and_prefix(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.put("a/b", BytesIO(b"hello"), "text/plain")
    store.put_bytes("a/c", b"world", "text/plain")
    assert store.get_bytes("a/b") == b"hello"
    with store.open("a/c") as stream:
        assert stream.read() == b"world"
    assert store.exists("a/b")
    store.delete("a/b")
    assert not store.exists("a/b")
    store.delete_prefix("a/")
    assert not store.exists("a/c")


@pytest.mark.parametrize("key", ["../outside", "/outside", "."])
def test_local_storage_rejects_traversal(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError, match="Invalid storage key"):
        LocalStore(tmp_path).put_bytes(key, b"x", "text/plain")
