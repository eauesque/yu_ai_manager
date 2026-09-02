"""Backward-compatible CLI entrypoint.

The implementation lives in `core/tagdb_core/tool/tagdb_tool_impl.py`.
This module re-exports legacy symbols so existing imports like
`import tagdb_tool; tagdb_tool.load_config_json(...)` keep working.
"""

import sys

from core.tagdb_core.tool.tagdb_tool_impl import *  # noqa: F401,F403

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))  # noqa: F405
