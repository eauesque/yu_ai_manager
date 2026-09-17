"""Extension API git/install lifecycle operations."""

import shutil

from .extensions_admin import install_requirements
from .extensions_api_git_helpers import (
    clone_repo,
    pull_repo_ff_only,
    repo_name_from_git_url,
)


def install_extension_from_git(mgr, git_url: str):
    ext_dir = mgr.extensions_dir
    ext_dir.mkdir(parents=True, exist_ok=True)
    repo_name = repo_name_from_git_url(git_url)
    if not repo_name or repo_name in (".", ".."):
        return {"error": "Invalid repository name"}, 400
    target_dir = (ext_dir / repo_name).resolve()
    if not target_dir.is_relative_to(ext_dir.resolve()):
        return {"error": "Invalid repository name (path traversal blocked)"}, 400
    if target_dir.exists():
        return {"error": f"Directory '{repo_name}' already exists. Uninstall first."}, 409
    clone_err, clone_status = clone_repo(git_url, target_dir)
    if clone_status != 200:
        return clone_err, clone_status

    manifest = mgr.load_single(target_dir)
    if manifest is None:
        shutil.rmtree(target_dir, ignore_errors=True)
        return {"error": "No valid manifest found in repository"}, 400
    manifest.source = "git"

    resp = {
        "message": f"Extension '{manifest.name}' installed successfully",
        "extension": mgr.get_extension_info(manifest.name),
        "warning": "⚠ Extensions can execute arbitrary code. Use at your own risk.",
    }
    pip_result = install_requirements(target_dir)
    if pip_result:
        resp["pip"] = pip_result
    return resp, 200


def update_extension_from_git(mgr, name: str):
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return {"error": f"Extension '{name}' not found"}, 404
    ext_dir = manifest.directory
    if ext_dir is None or not ext_dir.exists():
        return {"error": "Extension directory not found"}, 404
    if not (ext_dir / ".git").exists():
        return {"error": "Not a git repository — manual install cannot be updated via git"}, 400
    err, status, _stdout = pull_repo_ff_only(ext_dir)
    if status != 200:
        return err, status

    mgr.load_single(ext_dir)
    resp = {"message": f"Extension '{name}' updated", "extension": mgr.get_extension_info(name)}
    pip_result = install_requirements(ext_dir)
    if pip_result:
        resp["pip"] = pip_result
    return resp, 200


def update_all_git_extensions(mgr):
    results = []
    for ext_name, manifest in list(mgr.manifests.items()):
        ext_dir = manifest.directory
        if ext_dir is None or not ext_dir.exists():
            continue
        if not (ext_dir / ".git").exists():
            results.append({"name": ext_name, "status": "skipped", "reason": "not a git repository"})
            continue
        err, status, stdout = pull_repo_ff_only(ext_dir)
        if status != 200:
            results.append({"name": ext_name, "status": "error", "reason": err.get("detail") or err.get("error")})
            continue

        already_up_to_date = "Already up to date" in stdout or "Already up-to-date" in stdout
        pip_result = install_requirements(ext_dir)
        mgr.load_single(ext_dir)
        entry = {"name": ext_name, "status": "unchanged" if already_up_to_date else "updated"}
        if pip_result:
            entry["pip"] = pip_result
        results.append(entry)

    updated_count = sum(1 for r in results if r["status"] == "updated")
    return {
        "message": f"{updated_count} extension(s) updated",
        "total": len(results),
        "results": results,
    }


def uninstall_extension(mgr, name: str):
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return {"error": f"Extension '{name}' not found"}, 404
    ext_dir = manifest.directory
    mgr.unload(name)
    if ext_dir and ext_dir.exists():
        shutil.rmtree(ext_dir, ignore_errors=True)
    return {"message": f"Extension '{name}' uninstalled"}, 200
