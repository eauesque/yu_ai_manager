"""Compatibility facade for web_ui runtime.

Internal code should prefer ``runtime_app`` and ``runtime_runner`` directly.
This file remains to preserve the legacy ``core.web.runtime`` import path.
"""

from core.web.runtime_app import create_app
from core.web.runtime_runner import run_web_ui

__all__ = ["create_app", "run_web_ui"]
