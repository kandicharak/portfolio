from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HOST = "localhost"
PORT = 8503  # Use a distinct port to avoid conflicts
APP_FILE = "app.py"

def find_python_executable(root_dir: Path) -> str:
    # Try parent directory's venv
    venv_python = root_dir.parent / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False

def wait_for_port(host: str, port: int, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False

def launch_app_window(url: str, root_dir: Path) -> bool:
    browser_profile = root_dir.parent / ".app_browser_profile"
    browser_profile.mkdir(parents=True, exist_ok=True)

    edge_candidates = [
        shutil.which("msedge"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for edge in edge_candidates:
        if edge and Path(edge).exists():
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
    return False

def main() -> int:
    root_dir = Path(__file__).resolve().parent
    app_file = root_dir / APP_FILE
    
    if not app_file.exists():
        print(f"Missing app file: {app_file}")
        return 1

    python_exe = find_python_executable(root_dir)
    url = f"http://{HOST}:{PORT}"

    server_proc: subprocess.Popen[str] | None = None
    
    # 1. Start Streamlit UI
    if not is_port_open(HOST, PORT):
        cmd = [
            python_exe,
            "-m",
            "streamlit",
            "run",
            str(app_file),
            "--server.headless",
            "true",
            "--server.address",
            HOST,
            "--server.port",
            str(PORT),
            "--browser.gatherUsageStats",
            "false",
        ]
        server_proc = subprocess.Popen(cmd, cwd=str(root_dir))

    if not wait_for_port(HOST, PORT, timeout_seconds=30):
        print(f"Streamlit server did not start within timeout. Open {url} manually.")
        if server_proc is not None:
            server_proc.terminate()
        return 1

    # 2. Start Webview
    try:
        import webview
        webview.create_window(
            "Antigravity Live Dictation",
            url,
            width=1400,
            height=900,
            resizable=True,
        )
        print("Starting PyWebview...")
        webview.start(gui="edgechromium", debug=False)
        return 0
    except Exception as exc:
        print(f"pywebview could not start: {exc}")
        if launch_app_window(url, root_dir):
            print(f"Opened desktop app window at {url}")
            print("\nPress Ctrl+C in this console to stop the web server.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            return 0
        print(f"Could not open desktop app window automatically. Open {url} manually.")
        return 1
    finally:
        # Cleanup
        print("Cleaning up processes...")
        if server_proc is not None and server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

if __name__ == "__main__":
    raise SystemExit(main())
