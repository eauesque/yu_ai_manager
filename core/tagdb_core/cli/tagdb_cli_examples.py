"""Examples/epilog text for tagdb CLI parser."""


def legacy_cli_examples() -> str:
    return """Examples:
  # Initialize DB
  python tagdb_tool.py init --db tags.db

  # Scan one folder
  python tagdb_tool.py scan --db tags.db --root "D:\\images" --recursive --scan-zips

  # Manage scan roots in config.json
  python tagdb_tool.py add-root "D:\\images\\nai" --comment "main outputs"
  python tagdb_tool.py list-roots
  python tagdb_tool.py scan-all --db tags.db
  python tagdb_tool.py remove-root "D:\\images\\old"

  # Search
  python tagdb_tool.py search --db tags.db --q "1girl, -nsfw" --limit 100
  python tagdb_tool.py search --db tags.db --in-prompt "blue eyes" --from 2026-01-01 --to 2026-02-01
  python tagdb_tool.py search --db tags.db --file-name "2026-02" --regex

  # Maintenance
  python tagdb_tool.py cleanup --db tags.db --normalize-tags --dry-run
  python tagdb_tool.py find-duplicates --db tags.db --by-hash --cross-directory
  python tagdb_tool.py db-info --db tags.db

  # Debug logging (CLI args; env export remains supported)
  python tagdb_tool.py --debug-log on --debug-log-file logs/debug.log db-info --db tags.db
  python tagdb_tool.py --debug-log on --debug-log-stdout off scan --db tags.db --root "D:\\images"
"""
