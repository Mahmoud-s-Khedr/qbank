"""Object storage interfaces and implementations."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from shutil import copyfileobj
from typing import BinaryIO, Protocol

import boto3
from botocore.exceptions import ClientError

from qbank.config import get_settings


class ObjectStore(Protocol):
    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def open(self, key: str) -> BinaryIO: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...


class LocalStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path == self.root or not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as output:
            copyfileobj(fileobj, output)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.put(key, BytesIO(data), content_type)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        self._path(prefix)
        if self.root.exists():
            for item in self.root.rglob("*"):
                if item.is_file() and item.relative_to(self.root).as_posix().startswith(prefix):
                    item.unlink()


class S3Store:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        )
        self._ensured = False

    def ensure_bucket(self) -> None:
        if not self._ensured:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
                    raise
                self.client.create_bucket(Bucket=self.bucket)
            self._ensured = True

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self.ensure_bucket()
        self.client.upload_fileobj(
            fileobj, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.put(key, BytesIO(data), content_type)

    def open(self, key: str) -> BinaryIO:
        self.ensure_bucket()
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]  # type: ignore[return-value]  # StreamingBody is file-like.

    def get_bytes(self, key: str) -> bytes:
        with self.open(key) as stream:
            return stream.read()

    def exists(self, key: str) -> bool:
        self.ensure_bucket()
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def delete(self, key: str) -> None:
        self.ensure_bucket()
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        self.ensure_bucket()
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                self.delete(item["Key"])


@lru_cache
def get_store() -> ObjectStore:
    settings = get_settings()
    return (
        LocalStore(settings.storage_local_root)
        if settings.storage_backend == "local"
        else S3Store()
    )
