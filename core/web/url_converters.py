"""Custom Werkzeug URL converters for the Quart app."""

from werkzeug.routing import IntegerConverter

from core.infra_core.api_params import clamp_sqlite_int


class ClampedIntConverter(IntegerConverter):
    """`<int:...>` converter that clamps to SQLite's signed-64 range (prevents bind overflow -> 500)."""

    def to_python(self, value: str) -> int:
        return clamp_sqlite_int(super().to_python(value))
