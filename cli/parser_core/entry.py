"""CLI entrypoint implementation."""

import sys
from collections.abc import Sequence

from cli.parser_core.build import build_parser


def main(argv: Sequence[str]) -> int:
    parser = build_parser()

    if len(argv) == 0:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
