#!/usr/bin/env python3
"""
Port availability check script for ArgusAI.

Run before starting the server to ensure clean startup.
Can be used as ExecStartPre in systemd.

Usage:
    python scripts/check_port.py 8000
    python scripts/check_port.py 8000 --wait 30
    
Exit codes:
    0 - Port is available
    1 - Port is in use (and --wait timeout reached)
"""

import argparse
import socket
import sys
import time


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        return result != 0


def wait_for_port(host: str, port: int, timeout: int) -> bool:
    """Wait for a port to become available."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if is_port_available(host, port):
            elapsed = time.time() - start_time
            if elapsed > 0.1:
                print(f"Port {port} available after {elapsed:.1f}s")
            return True
        time.sleep(1)
    
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Check if a port is available for binding"
    )
    parser.add_argument(
        "port",
        type=int,
        help="Port number to check"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to check (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Wait up to SECONDS for port to become available"
    )
    
    args = parser.parse_args()
    
    if args.wait > 0:
        if not is_port_available(args.host, args.port):
            print(f"Port {args.port} in use, waiting up to {args.wait}s...")
            if not wait_for_port(args.host, args.port, args.wait):
                print(f"ERROR: Port {args.port} still in use after {args.wait}s", file=sys.stderr)
                print(f"Check: ss -tlnp | grep {args.port}", file=sys.stderr)
                sys.exit(1)
    else:
        if not is_port_available(args.host, args.port):
            print(f"ERROR: Port {args.port} is in use", file=sys.stderr)
            print(f"Check: ss -tlnp | grep {args.port}", file=sys.stderr)
            sys.exit(1)
    
    print(f"Port {args.port} is available")
    sys.exit(0)


if __name__ == "__main__":
    main()
