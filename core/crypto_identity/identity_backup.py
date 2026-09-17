"""Identity seed backup/restore CLI support.

The PEM wrapper is a project-specific encrypted container, not an OpenSSL
standard private-key format.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import os
import sys
from collections.abc import Callable
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from core.crypto_identity.identity import derive_peer_id
from core.crypto_identity.keypair import ed25519_pubkey_bytes

_HEADER = b"-----BEGIN ENCRYPTED ED25519 SEED-----"
_FOOTER = b"-----END ENCRYPTED ED25519 SEED-----"
_SCRYPT_N = 1048576
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_LEN = 32
_IV_LEN = 12
_SEED_LEN = 32
_AAD = b"yuai-identity-backup-v1"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(
        salt=salt,
        length=32,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    ).derive(passphrase.encode("utf-8"))


def _wrap_base64(raw: bytes) -> bytes:
    encoded = base64.b64encode(raw)
    lines = [encoded[i : i + 64] for i in range(0, len(encoded), 64)]
    return b"\n".join(lines)


def export_seed_to_pem(seed: bytes, *, passphrase: str) -> bytes:
    """Encrypt a 32-byte Ed25519 seed into the custom PEM-style format."""
    if len(seed) != _SEED_LEN:
        raise ValueError("ed25519 seed must be 32 bytes")
    if not passphrase:
        raise ValueError("passphrase is required")
    salt = os.urandom(_SALT_LEN)
    iv = os.urandom(_IV_LEN)
    key = _derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(iv, seed, _AAD)
    body = _wrap_base64(salt + iv + ciphertext)
    return _HEADER + b"\n" + body + b"\n" + _FOOTER + b"\n"


def import_seed_from_pem(pem: bytes, *, passphrase: str) -> bytes:
    """Decrypt a seed from the custom PEM-style format."""
    if not passphrase:
        raise ValueError("passphrase is required")
    lines = pem.splitlines()
    if not lines or lines[0].strip() != _HEADER or lines[-1].strip() != _FOOTER:
        raise ValueError("invalid identity backup wrapper")
    body = b"".join(line.strip() for line in lines[1:-1] if line.strip())
    try:
        raw = base64.b64decode(body, validate=True)
    except Exception as exc:
        raise ValueError("invalid identity backup body") from exc
    if len(raw) < _SALT_LEN + _IV_LEN + 16:
        raise ValueError("identity backup body is too short")
    salt = raw[:_SALT_LEN]
    iv = raw[_SALT_LEN : _SALT_LEN + _IV_LEN]
    ciphertext = raw[_SALT_LEN + _IV_LEN :]
    key = _derive_key(passphrase, salt)
    try:
        seed = AESGCM(key).decrypt(iv, ciphertext, _AAD)
    except Exception as exc:
        raise ValueError("decryption failed (wrong passphrase or corrupt file)") from exc
    if len(seed) != _SEED_LEN:
        raise ValueError("decrypted seed has invalid length")
    return seed


def read_seed_from_db(con) -> bytes | None:
    """Return the stored Ed25519 seed, or None when no identity exists."""
    row = con.execute(
        "SELECT value FROM lan_cowork_identity WHERE key='ed25519_seed'"
    ).fetchone()
    if row is None:
        return None
    return bytes(row[0])


def _describe_existing_seed(seed: bytes) -> str:
    try:
        return derive_peer_id(ed25519_pubkey_bytes(seed))
    except Exception:
        return "unknown"


def restore_seed_to_db(
    con,
    seed: bytes,
    *,
    force: bool = False,
    input_func: Callable[[str], str] = input,
) -> None:
    """UPSERT the seed, requiring OVERWRITE confirmation when one exists."""
    if len(seed) != _SEED_LEN:
        raise ValueError("ed25519 seed must be 32 bytes")
    existing = read_seed_from_db(con)
    if existing is not None and not force:
        peer_id = _describe_existing_seed(existing)
        print(f"既存の identity が存在します。peer_id={peer_id}")
        print("このコマンドは既存の identity を上書きし、すべてのペアリングを無効化します。")
        answer = input_func('続行する場合は "OVERWRITE" と入力: ')
        if answer != "OVERWRITE":
            raise PermissionError("identity import cancelled")
    con.execute(
        "INSERT OR REPLACE INTO lan_cowork_identity (key, value) VALUES ('ed25519_seed', ?)",
        (seed,),
    )
    con.execute("DELETE FROM peer_pairing_requests")
    con.execute("DELETE FROM peer_tokens")
    con.commit()


def export_identity(con, *, passphrase: str) -> bytes:
    seed = read_seed_from_db(con)
    if seed is None:
        raise RuntimeError("identity seed is not initialized")
    return export_seed_to_pem(seed, passphrase=passphrase)


def _prompt_new_passphrase() -> str:
    first = getpass.getpass("Passphrase: ")
    second = getpass.getpass("Confirm passphrase: ")
    if first != second:
        raise ValueError("passphrases do not match")
    return first


def _open_db(db_path: Path):
    from core.services_core.db_state import get_db, init_app_state

    init_app_state(db_path, {})
    return get_db()


def _cmd_export(args: argparse.Namespace) -> int:
    con = _open_db(Path(args.db))
    pem = export_identity(con, passphrase=_prompt_new_passphrase())
    Path(args.output).write_bytes(pem)
    print(f"Wrote identity backup: {args.output}")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    con = _open_db(Path(args.db))
    passphrase = getpass.getpass("Passphrase: ")
    seed = import_seed_from_pem(Path(args.file).read_bytes(), passphrase=passphrase)
    restore_seed_to_db(con, seed, force=args.force)
    print("Identity seed restored. Restart the service before pairing.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yuai identity")
    parser.add_argument(
        "--db",
        default=os.environ.get("TAGDB_DB", "data/tags.db"),
        help="Path to tags.db (default: data/tags.db, env: TAGDB_DB)",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    exp = sub.add_parser("export", help="Export encrypted identity seed backup")
    exp.add_argument("--output", required=True)
    exp.set_defaults(func=_cmd_export)
    imp = sub.add_parser("import", help="Import encrypted identity seed backup")
    imp.add_argument("file")
    imp.add_argument("--force", action="store_true")
    imp.set_defaults(func=_cmd_import)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (PermissionError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
