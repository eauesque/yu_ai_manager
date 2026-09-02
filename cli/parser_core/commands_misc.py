"""General-purpose CLI subcommands."""

from cli.commands import cmd_cleanup, cmd_db_info, cmd_find_duplicates, cmd_init, cmd_search


def register_misc_commands(sub) -> None:
    p_info = sub.add_parser("db-info", help="show database version and stats")
    p_info.add_argument("--db", required=True)
    p_info.set_defaults(func=cmd_db_info)

    p_init = sub.add_parser("init", help="initialize database")
    p_init.add_argument("--db", required=True)
    p_init.set_defaults(func=cmd_init)

    p_search = sub.add_parser("search", help="search indexed files")
    p_search.add_argument("--db", required=True)
    p_search.add_argument("--q", default=None)
    p_search.add_argument("--artist", default=None)
    p_search.add_argument("--in-prompt", default=None)
    p_search.add_argument("--from", dest="from_date", default=None, help="YYYY-MM-DD")
    p_search.add_argument("--to", dest="to_date", default=None, help="YYYY-MM-DD")
    p_search.add_argument("--limit", default=50, type=int)
    p_search.set_defaults(func=cmd_search)

    p_clean = sub.add_parser("cleanup", help="cleanup / dedupe DB")
    p_clean.add_argument("--db", required=True)
    p_clean.add_argument("--dedupe-paths", action="store_true")
    p_clean.add_argument("--prune-unused-tags", action="store_true")
    p_clean.add_argument("--mark-missing", action="store_true")
    p_clean.add_argument("--normalize-tags", action="store_true", help="normalize and merge duplicate tags (e.g. 'tag,' -> 'tag')")
    p_clean.add_argument("--vacuum", action="store_true")
    p_clean.add_argument("--dry-run", action="store_true")
    p_clean.set_defaults(func=cmd_cleanup)

    p_dupes = sub.add_parser("find-duplicates", help="find duplicate files")
    p_dupes.add_argument("--db", required=True)
    p_dupes.add_argument("--by-hash", action="store_true", help="find by content hash (accurate)")
    p_dupes.add_argument("--by-size", action="store_true", help="find by file size (fast but less accurate)")
    p_dupes.add_argument("--cross-directory", action="store_true", help="only show duplicates in different directories")
    p_dupes.add_argument("--delete", action="store_true", help="delete duplicates (keeps first occurrence)")
    p_dupes.set_defaults(func=cmd_find_duplicates)
