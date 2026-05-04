"""
MyTradingBot Launcher - Robust desktop application launcher
Handles port management, process lifecycle, and automatic window opening
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import threading
import atexit
from pathlib import Path


HOST = "localhost"
DEFAULT_PORT = 8765
PORT_SEARCH_RANGE = 50
APP_FILE = "streamlit_dhan_live_option_chain.py"

# Global reference to keep server process alive
_server_process: subprocess.Popen[str] | None = None


def find_available_port(host: str, preferred_port: int, search_range: int = PORT_SEARCH_RANGE) -> int:
    """Find an available port starting from preferred_port."""
    for port in range(preferred_port, preferred_port + search_range):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                continue  # Port is in use, try next
        except (OSError, socket.timeout):
            return port  # Port is available
    return preferred_port


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open (service is running)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, timeout_seconds: int = 30) -> bool:
    """Wait for a port to become available."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(0.3)
    return False


def find_python_executable(root_dir: Path) -> str:
    """Find the Python executable to use."""
    venv_python = root_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def launch_edge_window(url: str, root_dir: Path) -> bool:
    """Launch the app in an Edge window."""
    browser_profile = root_dir / ".app_browser_profile"
    try:
        browser_profile.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    edge_candidates = [
        shutil.which("msedge"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for edge in edge_candidates:
        if edge and Path(edge).exists():
            try:
                subprocess.Popen(
                    [
                        edge,
                        f"--app={url}",
                        "--new-window",
                        "--window-size=1400,900",
                        "--disable-extensions",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--user-data-dir={browser_profile}",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue

    chrome_candidates = [
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for chrome in chrome_candidates:
        if chrome and Path(chrome).exists():
            try:
                subprocess.Popen(
                    [
                        chrome,
                        f"--app={url}",
                        "--new-window",
                        "--window-size=1400,900",
                        "--disable-extensions",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--user-data-dir={browser_profile}",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue

    return False


def cleanup_on_exit() -> None:
    """Cleanup server process on exit."""
    global _server_process
    if _server_process is not None and _server_process.poll() is None:
        try:
            _server_process.terminate()
            _server_process.wait(timeout=5)
        except Exception:
            try:
                _server_process.kill()
            except Exception:
                pass


def start_server(python_exe: str, app_file: Path, host: str, port: int) -> bool:
    """Start the Streamlit server."""
    global _server_process
    
    cmd = [
        python_exe,
        "-m",
        "streamlit",
        "run",
        str(app_file),
        "--server.headless",
        "true",
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
    ]
    
    try:
        _server_process = subprocess.Popen(
            cmd,
            cwd=str(app_file.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return wait_for_port(host, port, timeout_seconds=30)
    except Exception as exc:
        return False


def main() -> int:
    """Main launcher entry point."""
    atexit.register(cleanup_on_exit)
    
    root_dir = Path(__file__).resolve().parent
    app_file = root_dir / APP_FILE
    
    if not app_file.exists():
        print(f"ERROR: Missing app file: {app_file}")
        input("Press Enter to exit...")
        return 1
    
    python_exe = find_python_executable(root_dir)
    
    # Find available port
    port = find_available_port(HOST, DEFAULT_PORT, PORT_SEARCH_RANGE)
    url = f"http://{HOST}:{port}"
    
    # Start server
    if not start_server(python_exe, app_file, HOST, port):
        print(f"ERROR: Could not start Streamlit server on {url}")
        input("Press Enter to exit...")
        return 1
    
    # Small delay to ensure server is fully ready
    time.sleep(1)
    
    # Launch window
    if not launch_edge_window(url, root_dir):
        print(f"WARNING: Could not open desktop window. Open {url} manually.")
        input("Press Enter to exit...")
        return 1
    
    print(f"✓ MyTradingBot launched on {url}")
    print("Keep this window open. Close it to stop the server.")
    
    # Keep process alive
    try:
        while _server_process and _server_process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
