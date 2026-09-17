"""Type stubs for sqlcipher3 — mirrors the sqlite3 standard library API."""
from sqlcipher3.dbapi2 import (
    Connection as Connection,
    Cursor as Cursor,
    DatabaseError as DatabaseError,
    Error as Error,
    IntegrityError as IntegrityError,
    NotSupportedError as NotSupportedError,
    OperationalError as OperationalError,
    PARSE_COLNAMES as PARSE_COLNAMES,
    PARSE_DECLTYPES as PARSE_DECLTYPES,
    ProgrammingError as ProgrammingError,
    Row as Row,
    connect as connect,
)
