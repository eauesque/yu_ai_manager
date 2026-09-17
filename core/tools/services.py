"""Service functions extracted from tools routes.

External-compatibility facade only.
Repo-internal imports should use the concrete implementation modules.
"""

from core.tools.services_file_search import file_search_service
from core.tools.services_inspect_upload import inspect_uploaded_file

__all__ = [
    "file_search_service",
    "inspect_uploaded_file",
]
