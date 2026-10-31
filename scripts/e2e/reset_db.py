"""Drop and recreate the throwaway e2e database (`reset`) or drop it (`drop`)."""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from qbank.config import get_settings


def main(action: str) -> None:
    url = make_url(get_settings().database_url)
    name = url.database
    if not name or not name.endswith("_e2e"):
        raise SystemExit(f"Refusing to touch database {name!r}: the e2e database must end in _e2e")
    engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        if action == "reset":
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reset")
