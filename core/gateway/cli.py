"""Bootstrap CLI for creating initial gateway keys without the admin UI."""
from __future__ import annotations

import argparse
import json
import secrets
import sys


def cmd_create_key(args: argparse.Namespace) -> None:
    from core.settings_core.secret_store import encrypt
    plain = secrets.token_urlsafe(32)
    entry = {
        "id": args.id,
        "secret_enc": encrypt(plain),
        "scopes": args.scopes,
        "allowed_models": args.models or None,
    }
    print(f"secret (copy now, shown once): {plain}")
    print("Add to config.json -> gateway.auth.api_keys:")
    print(json.dumps(entry, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m core.gateway.cli")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("create-key")
    p.add_argument("--id", required=True)
    p.add_argument("--scopes", nargs="+", default=["*"])
    p.add_argument("--models", nargs="*")
    args = parser.parse_args()
    if args.cmd == "create-key":
        cmd_create_key(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
