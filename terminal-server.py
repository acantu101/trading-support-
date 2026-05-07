#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
terminal-server.py -- WebSocket SSH Bridge for Trading Support Scenario Lab

Usage:
  pip install websockets paramiko
  python trading-support/terminal-server.py

Then open challenge-lab.html, click Scenario Lab on any deck, and press Connect.
The in-browser terminal will SSH into your configured VM.

Tested with Python 3.9+ and websockets 12.x / paramiko 3.x.
"""

import asyncio
import websockets
import paramiko
import os
import sys

# ---- SSH Configuration -------------------------------------------------------
SSH_CONFIG = {
    "hostname": "127.0.0.1",
    "port":     2222,        # hft VM: VirtualBox NAT Rule 1 (127.0.0.1:2222 -> :22)
    "username": "acm",
    "password": "11134",
    # "key_filename": os.path.expanduser("~/.ssh/id_rsa"),
    # "look_for_keys": False,
    # "allow_agent":   False,
}
WS_HOST = "localhost"
WS_PORT = 7681
# ------------------------------------------------------------------------------


async def handle(websocket):
    addr = websocket.remote_address
    print(f"[+] Connection from {addr}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        cfg = SSH_CONFIG.copy()
        if "key_filename" in cfg:
            cfg["key_filename"] = os.path.expanduser(cfg["key_filename"])
        client.connect(**cfg)
    except Exception as exc:
        err = f"\r\n\x1b[31m[SSH connection failed: {exc}]\x1b[0m\r\n"
        await websocket.send(err)
        print(f"[-] SSH failed for {addr}: {exc}")
        return

    channel = client.invoke_shell(term="xterm-256color", width=220, height=50)
    channel.setblocking(False)
    print(f"[+] Shell open for {addr}")

    stop = asyncio.Event()

    async def ssh_reader():
        """Forward SSH output to the WebSocket."""
        while not stop.is_set():
            try:
                if channel.recv_ready():
                    data = channel.recv(4096)
                    if not data:
                        break
                    await websocket.send(data)
                elif channel.exit_status_ready():
                    break
                else:
                    await asyncio.sleep(0.015)
            except Exception:
                break
        stop.set()

    async def ws_reader():
        """Forward WebSocket input to the SSH channel."""
        try:
            async for msg in websocket:
                if stop.is_set():
                    break
                channel.send(msg if isinstance(msg, bytes) else msg.encode())
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            stop.set()

    await asyncio.gather(ssh_reader(), ws_reader())

    channel.close()
    client.close()
    print(f"[+] Session ended for {addr}")


async def main():
    print("=" * 52)
    print("  Trading Support -- Scenario Lab Terminal Server  ")
    print("=" * 52)
    print(f"  WebSocket : ws://{WS_HOST}:{WS_PORT}")
    print(f"  SSH target: {SSH_CONFIG['username']}@{SSH_CONFIG['hostname']}:{SSH_CONFIG['port']}")
    print("  Press Ctrl+C to stop")
    print()

    async with websockets.serve(handle, WS_HOST, WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Stopped]")
    except OSError as exc:
        print(f"[Error] Cannot bind to port {WS_PORT}: {exc}")
        print("  Is another instance already running?")
        sys.exit(1)
