"""Write an uploaded file to disk from synchronous code.

Quart's ``FileStorage.save`` is a coroutine (Werkzeug's is not). Calling it
from a synchronous function -- which is what every upload handler here does,
because the work runs in a ``run_db_sync`` worker thread -- returns a coroutine
that nobody awaits: no file is created at all, and the caller then fails on a
path that does not exist. Measured on quart 0.20.0: after the sync call the
destination does not exist; a copy from ``.stream`` writes all 34 bytes.

Both classes expose a synchronous ``.stream``, so copying from it is correct
for either and needs no event loop.
"""

import shutil
from pathlib import Path
from typing import Any


def save_upload_sync(file_storage: Any, destination: str | Path) -> None:
    """Copy ``file_storage`` to ``destination`` without an event loop."""
    stream = file_storage.stream
    with open(destination, "wb") as out:
        shutil.copyfileobj(stream, out)
