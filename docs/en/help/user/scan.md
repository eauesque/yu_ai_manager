# Scanning

## Registering Scan Folders

Add folders to scan from Settings > Scan tab.

- Drag and drop to reorder
- Toggle folders on/off with the checkbox
- Multiple folders can be registered

## Running a Scan

- Scanning starts automatically after adding a folder
- Manual scans can be triggered from the Tools page or via the MCP `trigger_scan` tool
- Scan progress is reported in real time via SSE

## Auto Scan (Watcher)

Enable the Auto Scan Watcher extension to automatically detect file changes in registered folders and trigger scans.

## Remote File Systems

When scanning remote paths such as WSL / NAS / SMB, adjust the timeout settings in Settings > Remote FS tab.

## Scanning Large Libraries

Notes for scanning hundreds of thousands to over a million files:

- **Image search remains available during scans**: The search API uses a read-only DB connection, so it is unaffected by write locks during scanning
- **Automatic WAL management**: During scans, a WAL checkpoint is automatically performed every 2,000 files to prevent WAL file bloat
- **scan.db_busy event**: SSE events are sent at scan start/completion, allowing the frontend to display a busy indicator

## Scan Worker Process

Since v3.27.0, scans run in a separate process independent of web_ui.py.
This means **scans are not interrupted when web_ui is restarted**.

### How It Works

- When a scan is started from the WebUI, a worker process is launched in the background
- The worker writes progress files (JSON) and a PID file to `/tmp/yu-scan/`
- The WebUI polls this progress file and relays updates to the frontend via SSE
- When the WebUI is restarted, it automatically detects running workers and reconnects to their progress

### CLI Operation

The worker can also be operated directly from the CLI, even when the WebUI is stopped.

```bash
# Check status
python -m core.scan.scan_worker status

# Stop a running scan (graceful shutdown — saves resume position to DB)
python -m core.scan.scan_worker stop

# Start a scan directly from CLI
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# Options
#   --recursive / --no-recursive  Include subdirectories (default: recursive)
#   --scan-zips                   Scan images inside ZIP/7z archives
#   --force                       Re-scan existing files
#   --resume                      Resume an interrupted scan
#   --config config.json          Specify a config file
```

### Safety Mechanisms

- **Parent process monitoring**: Workers launched from the WebUI check the WebUI process every 60 seconds. If the WebUI terminates abnormally, the worker saves its progress and stops automatically
- **SIGTERM handling**: Sending SIGTERM via the `stop` command or `kill` allows the worker to finish its current task, commit to DB, save its resume position, and exit gracefully
- **Duplicate prevention**: Multiple workers cannot run simultaneously

### Troubleshooting

If the worker is unresponsive:

```bash
# Check the PID
cat /tmp/yu-scan/worker.pid

# Force-kill the process
kill -9 $(cat /tmp/yu-scan/worker.pid)

# Clean up leftover files
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## Scan Errors

If errors occur during scanning, you can check them via the MCP `get_scan_errors` tool.
