"""Find a free port in the test/debug range (5100-5999)."""
import socket
import sys


def find_free_port(start: int = 5100, end: int = 5999) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 5100
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 5999
    print(find_free_port(start, end))
