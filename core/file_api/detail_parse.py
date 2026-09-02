"""Re-export detail parsing helpers from core.

All logic now lives in core.prompt.detail_parsing; this module exists
for backward compatibility with existing route imports.
"""

from core.prompt.detail_parsing import (  # noqa: F401
    build_novelai_payload,
    resolve_detail_fields,
)
