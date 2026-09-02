#!/bin/bash
# Emergency stop for YU AI Manager (Unix)
PORT=${1:-5000}
HOST=${2:-127.0.0.1}

echo "=== YU AI Manager Emergency Stop ==="

# Try API stop first
python -m core.cli.emergency_stop --host "$HOST" --port "$PORT" 2>/dev/null

# If that fails, kill by PID
if [ -f data/server.pid ]; then
    PID=$(cat data/server.pid)
    echo "Sending SIGTERM to PID $PID..."
    kill "$PID" 2>/dev/null
    sleep 5
    if kill -0 "$PID" 2>/dev/null; then
        echo "SIGTERM failed, sending SIGKILL..."
        kill -9 "$PID" 2>/dev/null
    fi
else
    echo "No PID file. Killing by port $PORT..."
    fuser -k "$PORT/tcp" 2>/dev/null || lsof -ti :"$PORT" | xargs kill -9 2>/dev/null
fi

echo "Done."
