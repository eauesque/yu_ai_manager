"""Shared mutable state for license audit runs."""

from dataclasses import dataclass


@dataclass
class AuditState:
    passed: int = 0
    failed: int = 0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        line = f"  [{status}] {label}"
        if detail:
            line += f" -- {detail}"
        print(line)
