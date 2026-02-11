"""Startup utilities for ArgusAI backend.

Includes port availability checks to prevent binding issues during restarts (Issue #383).
"""

import socket
import time
import logging

logger = logging.getLogger(__name__)


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding.
    
    Args:
        host: Host address to check
        port: Port number to check
        
    Returns:
        True if port is available, False if in use
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        return result != 0  # 0 means connection succeeded (port in use)


def wait_for_port(
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: int = 30,
    interval: float = 1.0
) -> bool:
    """Wait for a port to become available.
    
    Useful during restarts when the previous process may still be releasing the port.
    
    Args:
        host: Host address to check (default: 127.0.0.1)
        port: Port number to wait for (default: 8000)
        timeout: Maximum seconds to wait (default: 30)
        interval: Seconds between checks (default: 1.0)
        
    Returns:
        True if port became available, False if timeout reached
        
    Example:
        >>> if not wait_for_port(port=8000, timeout=30):
        ...     raise RuntimeError("Port 8000 still in use after 30s")
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if is_port_available(host, port):
            elapsed = time.time() - start_time
            if elapsed > 0.1:  # Only log if we actually waited
                logger.info(f"Port {port} available after {elapsed:.1f}s")
            return True
        
        logger.debug(f"Port {port} still in use, waiting {interval}s...")
        time.sleep(interval)
    
    logger.warning(f"Port {port} still in use after {timeout}s timeout")
    return False


def check_startup_requirements(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run startup checks before binding.
    
    Call this before starting uvicorn to ensure clean startup.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        
    Raises:
        RuntimeError: If startup requirements are not met
    """
    # Check port availability (with short wait for restart scenarios)
    check_host = "127.0.0.1" if host == "0.0.0.0" else host
    
    if not is_port_available(check_host, port):
        logger.info(f"Port {port} in use, waiting for release...")
        if not wait_for_port(check_host, port, timeout=15):
            raise RuntimeError(
                f"Port {port} is still in use after waiting. "
                f"Check for zombie processes: sudo ss -tlnp | grep {port}"
            )
    
    logger.info(f"Startup checks passed, port {port} available")
