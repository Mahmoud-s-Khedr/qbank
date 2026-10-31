"""Per-process, streaming PDF cache with leased entries and LRU eviction."""

import atexit
import hashlib
import os
import shutil
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from qbank.config import get_settings
from qbank.storage import ObjectStore


class PdfCache:
    def __init__(self, directory: str | None, max_mb: int) -> None:
        if directory is not None:
            Path(directory).mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="qbank-pdf-", dir=directory))
        self.max_bytes = max_mb * 1024 * 1024
        self.guard = threading.Lock()
        self.locks: dict[str, threading.Lock] = {}
        self.active: dict[str, int] = {}
        atexit.register(shutil.rmtree, self.root, ignore_errors=True)

    def _evict(self) -> None:
        entries = sorted(self.root.glob("*.pdf"), key=lambda path: path.stat().st_mtime_ns)
        total = sum(path.stat().st_size for path in entries)
        for path in entries:
            if total <= self.max_bytes:
                break
            if self.active.get(path.stem, 0):
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size

    @contextmanager
    def acquire(self, key: str, store: ObjectStore) -> Iterator[Path]:
        digest = hashlib.sha256(key.encode()).hexdigest()
        path = self.root / f"{digest}.pdf"
        with self.guard:
            lock = self.locks.setdefault(digest, threading.Lock())
            self.active[digest] = self.active.get(digest, 0) + 1
        try:
            with lock:
                if not path.exists():
                    fd, name = tempfile.mkstemp(dir=self.root, prefix="download-")
                    try:
                        with os.fdopen(fd, "wb") as output, store.open(key) as source:
                            shutil.copyfileobj(source, output)
                        os.replace(name, path)
                    finally:
                        Path(name).unlink(missing_ok=True)
                with self.guard:
                    os.utime(path, None)
                    self._evict()
            yield path
        finally:
            with self.guard:
                self.active[digest] -= 1
                if not self.active[digest]:
                    del self.active[digest]
                self._evict()


@lru_cache
def get_pdf_cache() -> PdfCache:
    settings = get_settings()
    return PdfCache(settings.worker_cache_dir, settings.worker_cache_max_mb)
