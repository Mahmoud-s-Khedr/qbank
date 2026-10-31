from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def database_ok(db: Session) -> bool:
    try:
        db.execute(text("SET LOCAL statement_timeout = '2s'"))
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def redis_ok() -> bool:
    from redis import Redis  # noqa: PLC0415

    from qbank.config import get_settings  # noqa: PLC0415

    try:
        return bool(
            Redis.from_url(
                get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
            ).ping()
        )
    except Exception:
        return False


def storage_ok() -> bool:
    import boto3  # noqa: PLC0415
    from botocore.config import Config  # noqa: PLC0415

    from qbank.config import get_settings  # noqa: PLC0415
    from qbank.storage import LocalStore, S3Store, get_store  # noqa: PLC0415

    try:
        store = get_store()
        if isinstance(store, LocalStore):
            return store.root.is_dir()
        if isinstance(store, S3Store):
            settings = get_settings()
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
                config=Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 0}),
            )
            client.head_bucket(Bucket=store.bucket)
            return True
    except Exception:
        return False
    return False


def readiness_database_ok() -> bool:
    from qbank.db import get_engine  # noqa: PLC0415

    try:
        with Session(get_engine()) as db:
            return database_ok(db)
    except Exception:
        return False
