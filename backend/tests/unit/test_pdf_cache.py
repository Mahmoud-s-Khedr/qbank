from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import BinaryIO

import pytest

from qbank.pipeline.pdf_cache import PdfCache
from qbank.storage import LocalStore


class CountingStore(LocalStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.opens = 0
        self.lock = Lock()

    def open(self, key: str) -> BinaryIO:
        with self.lock:
            self.opens += 1
        return super().open(key)


def test_cache_streams_once_per_key_and_evicts(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / "store")
    store.put_bytes("one", b"a" * 600000, "application/pdf")
    store.put_bytes("two", b"b" * 600000, "application/pdf")
    cache = PdfCache(str(tmp_path / "cache"), 1)

    def get(_: int) -> bytes:
        with cache.acquire("one", store) as path:
            return path.read_bytes()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(data == b"a" * 600000 for data in pool.map(get, range(8)))
    assert store.opens == 1
    with cache.acquire("two", store) as path:
        assert path.read_bytes() == b"b" * 600000
    with cache.acquire("one", store):
        pass
    assert store.opens == len(("one", "two", "one"))


def test_cache_removes_failed_download(tmp_path: Path) -> None:
    cache = PdfCache(str(tmp_path), 1)
    with (
        pytest.raises(FileNotFoundError),
        cache.acquire("missing", LocalStore(tmp_path / "missing")),
    ):
        pass
    assert list(cache.root.iterdir()) == []
