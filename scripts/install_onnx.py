"""Detect GPU and install the appropriate onnxruntime variant via uv extras.

The onnxruntime variants are declared as mutually exclusive extras in
``pyproject.toml`` (``cpu`` / ``gpu`` / ``directml`` / ``rocm``). This script:

1. detects the machine's accelerator (via ``scripts/detect_onnx_extra.py``)
2. writes the chosen extra name to ``.onnx_extra`` (read by start.bat /
   start.sh on subsequent launches so we don't redetect every time)
3. runs ``uv sync --extra <variant>`` to install the matching wheel

Manual override: edit ``.onnx_extra`` to one of cpu / gpu / directml / rocm
and re-run this script (or ``uv sync --extra <variant>``) to apply.

Usage:
    uv run python scripts/install_onnx.py [--force] [--variant {cpu,gpu,directml,rocm}]
    uv run --no-project python scripts/install_onnx.py --repair --variant gpu
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MARKER_FILE = PROJECT_ROOT / ".onnx_extra"
VALID_EXTRAS = ("cpu", "gpu", "directml", "rocm", "silicon")
_ORT_CLEANUP_NAMES = ("onnxruntime",)
_ORT_DIST_PATTERNS = ("onnxruntime-*.dist-info", "onnxruntime_gpu-*.dist-info")


def _uv_cmd() -> str | None:
    return shutil.which("uv")


def _detect() -> str:
    """Run detect_onnx_extra.py as a subprocess so we share one source of truth."""
    detect_script = PROJECT_ROOT / "scripts" / "detect_onnx_extra.py"
    r = subprocess.run(
        [sys.executable, str(detect_script)],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip() or "cpu"


def _read_marker() -> str | None:
    if not MARKER_FILE.exists():
        return None
    val = MARKER_FILE.read_text(encoding="utf-8").strip()
    return val if val in VALID_EXTRAS else None


def _write_marker(extra: str) -> None:
    MARKER_FILE.write_text(extra + "\n", encoding="utf-8")


def _site_packages_dirs() -> list[Path]:
    venv = PROJECT_ROOT / ".venv"
    candidates = [venv / "Lib" / "site-packages"]
    candidates.extend((venv / "lib").glob("python*/site-packages"))
    return [p for p in candidates if p.exists()]


def _collect_onnxruntime_cleanup_targets(site_packages_dirs: list[Path]) -> list[Path]:
    targets: list[Path] = []
    for site_packages in site_packages_dirs:
        for name in _ORT_CLEANUP_NAMES:
            target = site_packages / name
            if target.exists():
                targets.append(target)
        for pattern in _ORT_DIST_PATTERNS:
            targets.extend(sorted(site_packages.glob(pattern)))
    return sorted(dict.fromkeys(targets))


def _has_mixed_onnxruntime_dist_info(site_packages_dirs: list[Path]) -> bool:
    for site_packages in site_packages_dirs:
        has_cpu = any(site_packages.glob("onnxruntime-*.dist-info"))
        has_gpu = any(site_packages.glob("onnxruntime_gpu-*.dist-info"))
        if has_cpu and has_gpu:
            return True
    return False


def _project_python() -> Path | None:
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _probe_onnxruntime(extra: str) -> bool:
    python = _project_python()
    if python is None:
        return True

    code = (
        "import importlib.metadata as m\n"
        "import onnxruntime as ort\n"
        "getattr(ort, '__version__')\n"
        "providers = ort.get_available_providers()\n"
        "m.version('onnxruntime-gpu')\n"
        "raise SystemExit(0 if 'CUDAExecutionProvider' in providers else 2)\n"
    )
    if extra != "gpu":
        code = (
            "import onnxruntime as ort\n"
            "getattr(ort, '__version__')\n"
            "ort.get_available_providers()\n"
        )
    r = subprocess.run([str(python), "-c", code], cwd=PROJECT_ROOT)
    return r.returncode == 0


def _find_onnxruntime_problem(
    extra: str,
    site_packages_dirs: list[Path],
    *,
    probe_ok: bool | None = None,
) -> str | None:
    if extra != "gpu":
        return None
    if _has_mixed_onnxruntime_dist_info(site_packages_dirs):
        return "mixed onnxruntime CPU/GPU dist-info"
    if probe_ok is None:
        probe_ok = _probe_onnxruntime(extra)
    if not probe_ok:
        return "onnxruntime GPU probe failed"
    return None


def _remove_path_inside_site_packages(target: Path, site_packages_dirs: list[Path]) -> None:
    resolved = target.resolve()
    allowed_roots = [p.resolve() for p in site_packages_dirs]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise RuntimeError(f"Refusing to remove outside site-packages: {target}")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def _repair_onnxruntime(extra: str) -> bool:
    site_packages_dirs = _site_packages_dirs()
    problem = _find_onnxruntime_problem(extra, site_packages_dirs)
    if problem is None:
        return False

    print(f"  onnxruntime repair: {problem}")
    for target in _collect_onnxruntime_cleanup_targets(site_packages_dirs):
        print(f"  remove: {target}")
        _remove_path_inside_site_packages(target, site_packages_dirs)

    cmd = [_uv_cmd() or "uv", "sync", "--extra", extra, "--reinstall-package", "onnxruntime-gpu"]
    print(f"  $ {' '.join(cmd)}")
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str(PROJECT_ROOT / ".uv-cache-local"))
    r = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)
    if r.returncode != 0:
        print("エラー: onnxruntime-gpu の自動修復に失敗しました。", file=sys.stderr)
        sys.exit(r.returncode)
    if not _probe_onnxruntime(extra):
        print("エラー: 修復後も CUDAExecutionProvider を検出できません。", file=sys.stderr)
        sys.exit(1)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="既存マーカーを無視して再検出する")
    parser.add_argument("--repair", action="store_true", help="壊れた onnxruntime GPU 環境を検出した場合だけ修復する")
    parser.add_argument(
        "--variant",
        choices=VALID_EXTRAS,
        help="検出を行わずに指定された extra を使う（手動オーバーライド）: cpu/gpu/directml/rocm/silicon",
    )
    args = parser.parse_args()

    uv_cmd = _uv_cmd()
    if uv_cmd is None:
        print("エラー: uv が見つかりません。https://docs.astral.sh/uv/ を参照してインストールしてください。", file=sys.stderr)
        sys.exit(1)

    if args.variant:
        extra = args.variant
        print(f"  指定された variant: {extra}")
    else:
        cached = None if args.force else _read_marker()
        if cached:
            extra = cached
            print(f"  キャッシュされた variant: {extra}  ({MARKER_FILE.name} 由来。再検出するには --force)")
        else:
            extra = _detect()
            print(f"  検出された variant: {extra}")

    _write_marker(extra)
    print(f"  marker 更新: {MARKER_FILE} -> {extra}")

    if args.repair:
        repaired = _repair_onnxruntime(extra)
        if repaired:
            print("\n✓ onnxruntime GPU 環境を修復しました。")
        return

    cmd = [uv_cmd, "sync", "--extra", extra]
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if r.returncode != 0:
        print(f"エラー: uv sync --extra {extra} に失敗しました。", file=sys.stderr)
        sys.exit(r.returncode)

    print(f"\n✓ onnxruntime ({extra}) のインストールが完了しました。")
    print("  起動スクリプト (start.bat / start.sh) は次回以降このマーカーを読み取ります。")


if __name__ == "__main__":
    main()
