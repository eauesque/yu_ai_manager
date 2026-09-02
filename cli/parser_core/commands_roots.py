"""Scan-root management CLI subcommands."""

from cli.commands import cmd_add_root, cmd_list_roots, cmd_remove_root


def register_root_commands(sub) -> None:
    p_add_root = sub.add_parser("add-root", help="add scan root to config.json")
    p_add_root.add_argument("path", help="directory path to add")
    p_add_root.add_argument("--recursive", action="store_true", default=True, help="scan recursively (default: true)")
    p_add_root.add_argument("--enabled", action="store_true", default=True, help="enable this root (default: true)")
    p_add_root.add_argument("--comment", default="", help="optional comment")
    p_add_root.set_defaults(func=cmd_add_root)

    p_list_roots = sub.add_parser("list-roots", help="list all scan roots from config.json")
    p_list_roots.set_defaults(func=cmd_list_roots)

    p_remove_root = sub.add_parser("remove-root", help="remove scan root from config.json")
    p_remove_root.add_argument("path", help="directory path to remove")
    p_remove_root.set_defaults(func=cmd_remove_root)
