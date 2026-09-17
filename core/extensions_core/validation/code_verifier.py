"""Code Verifier (judicial): AST static analysis of extension code.

Corresponds to the "judicial" branch of the separation-of-powers model,
validating that extension Python code stays within the permissions
declared in the manifest.

Builtin (TrustLevel.TRUSTED) extensions skip scanning (auto-approved).
"""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

from core.extensions_core.extensions_defs import TrustLevel

logger = logging.getLogger(__name__)

# Import module name -> required permission mapping
# VIOLATION:* is always blocked regardless of trust_level
IMPORT_PERMISSION_MAP: dict[str, str] = {
    "subprocess": "subprocess",
    "os": "subprocess",          # os.system / os.popen / os.exec* require subprocess perm
    "requests": "network:internet",
    "urllib.request": "network:internet",
    "urllib3": "network:internet",
    "httpx": "network:internet",
    "aiohttp": "network:internet",
    "socket": "network:internet",
    "http.client": "network:internet",
    "sqlite3": "VIOLATION:direct_db",
    "ctypes": "VIOLATION:native_code",
    "importlib": "VIOLATION:dynamic_import",
}

# Dynamic code execution patterns (function/method names)
DYNAMIC_EXEC_PATTERNS: set[str] = {
    "eval", "exec", "__import__", "compile",
    # os-level process spawning (attr-name match — false-pos acceptable in security scan)
    "system", "popen",
}


@dataclass
class CodeFinding:
    """Issue detected by static analysis."""
    file: str
    line: int
    severity: str   # "block", "warn", "info"
    message: str


@dataclass
class CodeVerdict:
    """Code verification result."""
    approved: bool = True
    findings: list[CodeFinding] = field(default_factory=list)


class CodeVerifier:
    """Performs AST static analysis on extension code."""

    def verify(
        self,
        ext_dir: Path,
        trust_level: str,
        granted_permissions: set[str],
    ) -> CodeVerdict:
        """Analyze all .py files in the extension directory.

        Args:
            ext_dir: Extension directory path
            trust_level: TrustLevel value
            granted_permissions: Set of user-approved permissions

        Returns:
            CodeVerdict: verification result
        """
        verdict = CodeVerdict()

        # L0 (builtin) is auto-approved
        if trust_level == TrustLevel.TRUSTED:
            return verdict

        ext_dir_resolved = ext_dir.resolve()
        py_files = [
            f for f in ext_dir.rglob("*.py")
            if f.resolve().is_relative_to(ext_dir_resolved)
        ]
        if not py_files:
            return verdict

        for py_file in py_files:
            # Skip __pycache__
            if "__pycache__" in str(py_file):
                continue
            self._analyze_file(
                py_file, ext_dir, trust_level, granted_permissions, verdict
            )

        # Reject if any block-level findings exist
        if any(f.severity == "block" for f in verdict.findings):
            verdict.approved = False

        return verdict

    def _analyze_file(
        self,
        py_file: Path,
        ext_dir: Path,
        trust_level: str,
        granted_permissions: set[str],
        verdict: CodeVerdict,
    ) -> None:
        """Analyze a single Python file via AST."""
        rel_path = str(py_file.relative_to(ext_dir))

        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as e:
            verdict.findings.append(CodeFinding(
                file=rel_path,
                line=e.lineno or 0,
                severity="block",
                message=f"構文エラー: {e.msg}",
            ))
            return

        for node in ast.walk(tree):
            # Inspect import statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_import(
                        alias.name, rel_path, node.lineno,
                        trust_level, granted_permissions, verdict,
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                self._check_import(
                    node.module, rel_path, node.lineno,
                    trust_level, granted_permissions, verdict,
                )

            # Inspect dynamic code execution patterns
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in DYNAMIC_EXEC_PATTERNS:
                    severity = "block" if trust_level == TrustLevel.UNTRUSTED else "warn"
                    verdict.findings.append(CodeFinding(
                        file=rel_path,
                        line=node.lineno,
                        severity=severity,
                        message=f"動的コード実行 '{func_name}()' が検出されました",
                    ))

    def _check_import(
        self,
        module_name: str,
        rel_path: str,
        lineno: int,
        trust_level: str,
        granted_permissions: set[str],
        verdict: CodeVerdict,
    ) -> None:
        """Check whether an import statement triggers the permission map."""
        # Search by exact or prefix match
        required_perm = None
        for import_pattern, perm in IMPORT_PERMISSION_MAP.items():
            if module_name == import_pattern or module_name.startswith(import_pattern + "."):
                required_perm = perm
                break

        if required_perm is None:
            return

        # VIOLATION: always blocked
        if required_perm.startswith("VIOLATION:"):
            violation_type = required_perm.split(":", 1)[1]
            verdict.findings.append(CodeFinding(
                file=rel_path,
                line=lineno,
                severity="block",
                message=f"禁止モジュール '{module_name}' の import ({violation_type})",
            ))
            return

        # Check if permission is in declared permissions
        if required_perm not in granted_permissions:
            verdict.findings.append(CodeFinding(
                file=rel_path,
                line=lineno,
                severity="block",
                message=(
                    f"'{module_name}' の import には '{required_perm}' "
                    f"権限が必要ですが宣言されていません"
                ),
            ))

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        """Retrieve the function name from a call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""
