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
