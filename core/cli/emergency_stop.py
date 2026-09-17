"""Emergency stop CLI — sends stop commands to all running operations."""

import argparse
import contextlib
import json
import os
import signal
import urllib.error
import urllib.request


def _post(base_url: str, path: str, pin: str = "") -> dict:
    """Send POST to the server API."""
    url = f"{base_url}{path}"
    headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
    if pin:
        headers["Authorization"] = f"Bearer {pin}"
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


STOP_ENDPOINTS = [
    "/api/scan/stop",
    "/ext/hailo-semantic/api/index/stop",
    "/ext/hailo-yolo/api/detect/stop",
    "/ext/speech-to-text/api/s2t/stream/stop",
]


def main():
    parser = argparse.ArgumentParser(description="Emergency stop for YU AI Manager")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--pin", default="")
    parser.add_argument("--kill", action="store_true", help="Kill process if API fails")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    print(f"Sending stop commands to {base_url}...")

    success = 0
    for ep in STOP_ENDPOINTS:
        result = _post(base_url, ep, args.pin)
        status = result.get("error", "OK")
        print(f"  {ep}: {status}")
        if "error" not in result:
            success += 1

    print(f"\n{success}/{len(STOP_ENDPOINTS)} stopped.")

    if args.kill:
        _kill_process(args.port)


def _kill_process(port: int):
    """Kill the server process by port."""
    pid_file = os.path.join("data", "server.pid")
    pid = None

    if os.path.exists(pid_file):
        with contextlib.suppress(ValueError, OSError), open(pid_file) as pid_f:
            pid = int(pid_f.read().strip())

    if pid:
        print(f"Killing PID {pid}...")
        try:
            os.kill(pid, signal.SIGTERM)
            print("SIGTERM sent.")
        except OSError as e:
            print(f"Failed: {e}")
    else:
        print(f"No PID file found. Use OS tools to kill process on port {port}.")


if __name__ == "__main__":
    main()
