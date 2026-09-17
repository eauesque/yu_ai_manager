"""Filter expression dataclass for extension search hooks."""

from dataclasses import dataclass
from typing import Any


@dataclass
class FilterExpr:
    field: str
    operator: str
    value: Any

    ALLOWED_OPERATORS = frozenset({"=", "!=", "<>", "LIKE", "NOT LIKE", ">=", "<=", ">", "<", "IN", "NOT IN", "REGEXP"})
    ALLOWED_FIELDS = frozenset(
        {
            "f.id",
            "f.path",
            "f.mtime",
            "f.size",
            "f.meta_source",
            "f.is_deleted",
            "f.content_hash",
            "t.tag",
            "t.namespace",
            "ft.weight",
            "tm.raw_prompt",
            "tm.raw_negative",
            "tm.raw_meta_json",
            "tm.model_name",
            "tm.model_hash",
        }
    )

    def validate(self) -> bool:
        op = self.operator.upper()
        return op in self.ALLOWED_OPERATORS and self.field in self.ALLOWED_FIELDS

    def to_sql(self) -> tuple[str, list[Any]]:
        if not self.validate():
            raise ValueError(f"Invalid filter: field={self.field!r} op={self.operator!r}")
        op = self.operator.upper()
        if op in ("IN", "NOT IN"):
            if not isinstance(self.value, (list, tuple)):
                raise ValueError(f"IN/NOT IN requires list value, got {type(self.value)}")
            placeholders = ", ".join("?" for _ in self.value)
            return f"{self.field} {op} ({placeholders})", list(self.value)
        return f"{self.field} {op} ?", [self.value]
