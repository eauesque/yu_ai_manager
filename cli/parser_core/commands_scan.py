"""Scan-related CLI subcommands."""

from cli.commands import cmd_scan, cmd_scan_all


def register_scan_commands(sub) -> None:
    p_scan = sub.add_parser("scan", help="scan folder and index")
    p_scan.add_argument("--db", required=True)
    p_scan.add_argument("--root", required=True)
    p_scan.add_argument("--recursive", action="store_true")
    p_scan.add_argument("--exts", default=".png,.jpg,.jpeg,.webp,.webm,.svg")
    p_scan.add_argument("--mark-deleted", action="store_true")
    p_scan.add_argument("--force", action="store_true", help="force re-parse even if unchanged")
    p_scan.add_argument("--compute-hash", action="store_true", help="compute ETag (SHA1 full or partial) to enable 304(not modified) skipping")
    p_scan.add_argument("--scan-zips", action="store_true", help="also scan images inside ZIP files")
    p_scan.set_defaults(func=cmd_scan)

    p_scan_all = sub.add_parser("scan-all", help="scan all roots from config.json")
    p_scan_all.add_argument("--db", required=True)
    p_scan_all.add_argument("--force", action="store_true", help="force re-parse even if unchanged")
    p_scan_all.set_defaults(func=cmd_scan_all)
