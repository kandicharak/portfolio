#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LEVEL 15: THE LOCAL BROADCAST
Broadcasts the Web Dashboard to the local network via HTTP server.
"""

import http.server
import socket
import os
import sys

# Configuration
PORT = 8000
WEB_FOLDER = r"d:\autonomus\generated_project\web_dashboard"


def get_local_ip():
    """Get the machine's local IP address using socket."""
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        return ip_address
    except Exception as e:
        print("\n[WARNING] Could not determine local IP: " + str(e))
        print("   Using fallback IP detection...\n")
        # Fallback: try to get all network interfaces
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
        except Exception:
            ip_address = "127.0.0.1"
        finally:
            s.close()
        return ip_address


def main():
    """Start the HTTP server and broadcast the dashboard."""
    
    # Get local IP address
    local_ip = get_local_ip()
    
    # Print broadcast message
    print("\n" + "=" * 70)
    print("SYSTEM LIVE ON NETWORK!")
    print("=" * 70)
    print("\n[LOCAL IP ADDRESS]: " + str(local_ip))
    print("[PHONE ACCESS URL]: http://" + str(local_ip) + ":" + str(PORT) + "/LIVE_MONITOR.html")
    print("[SERVING FOLDER]: " + WEB_FOLDER)
    print("[SERVER PORT]: " + str(PORT))
    print("\n" + "=" * 70)
    
    # Create HTTP server handler
    class DashboardHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=WEB_FOLDER, **kwargs)
        
        def log_message(self, format, *args):
            print("[SERVER] " + str(args[0]))
    
    # Start server
    server_address = ("", PORT)
    httpd = http.server.HTTPServer(server_address, DashboardHandler)
    
    print("\n[SERVER RUNNING]: http://" + str(local_ip) + ":" + str(PORT))
    print("Press Ctrl+C to stop the broadcast...\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n[BROADCAST TERMINATED] by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
