from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "identity":
        from core.crypto_identity.identity_backup import main as identity_main

        return identity_main(args[1:])
    print("Usage: python -m yuai identity {export,import} ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
