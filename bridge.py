#!/usr/bin/env python3
"""
Claude Code Terminal Mirror — iTerm2 API Bridge

Streams your iTerm terminal to your phone over WiFi.
No tmux required. Laptop terminal stays at full size.

Usage:
  source .venv/bin/activate
  python bridge.py [--port 8800] [--session SESSION_ID]
"""

import asyncio
import json
import os
import secrets
import socket
import argparse
from typing import Optional

import iterm2
import websockets
from websockets.asyncio.server import serve as ws_serve


def get_lan_ip() -> Optional[str]:
    """Detect LAN IP address, preferring WiFi over VPN."""
    # Parse en0 (WiFi on macOS) from ifconfig
    try:
        import subprocess
        result = subprocess.run(["ifconfig"], capture_output=True, text=True)
        # Parse ifconfig output for en0 (WiFi on macOS)
        lines = result.stdout.split("\n")
        in_en0 = False
        for line in lines:
            if line.startswith("en0:"):
                in_en0 = True
            elif line and not line.startswith("\t") and not line.startswith(" "):
                in_en0 = False
            elif in_en0 and "inet " in line:
                parts = line.strip().split()
                idx = parts.index("inet") + 1
                if idx < len(parts):
                    return parts[idx]
    except Exception:
        pass

    # Fallback: UDP trick
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
            return ip
    except Exception:
        pass
    return None


def generate_token() -> str:
    """Generate a human-friendly two-word token."""
    adjectives = [
        "brave", "calm", "dark", "eager", "fair", "glad", "happy", "keen",
        "lively", "mellow", "noble", "proud", "quick", "rapid", "sharp",
        "swift", "tall", "vast", "warm", "wise", "bold", "cool", "deep",
        "fast", "gentle", "kind", "lucky", "neat", "quiet", "silent",
    ]
    nouns = [
        "river", "storm", "cloud", "flame", "frost", "grove", "hawk",
        "lake", "maple", "oak", "peak", "rain", "sage", "stone", "tiger",
        "wave", "wolf", "cedar", "dawn", "eagle", "falcon", "harbor",
        "jade", "marsh", "panda", "ridge", "spark", "trail", "vine", "willow",
    ]
    return f"{secrets.choice(adjectives)}_{secrets.choice(nouns)}"


def style_to_ansi(style, text: str) -> str:
    """Convert iTerm CellStyle to ANSI escape codes wrapping the text."""
    codes = []

    if style.bold:
        codes.append("1")
    if style.faint:
        codes.append("2")
    if style.italic:
        codes.append("3")
    if style.underline:
        codes.append("4")
    if style.blink:
        codes.append("5")
    if style.inverse:
        codes.append("7")
    if style.strikethrough:
        codes.append("9")

    fg = style.fg_color
    if fg.is_rgb:
        r, g, b = fg.rgb
        codes.append(f"38;2;{r};{g};{b}")
    elif fg.is_standard:
        idx = fg.standard
        if idx < 8:
            codes.append(str(30 + idx))
        elif idx < 16:
            codes.append(str(90 + idx - 8))
        else:
            codes.append(f"38;5;{idx}")

    bg = style.bg_color
    if bg.is_rgb:
        r, g, b = bg.rgb
        codes.append(f"48;2;{r};{g};{b}")
    elif bg.is_standard:
        idx = bg.standard
        if idx < 8:
            codes.append(str(40 + idx))
        elif idx < 16:
            codes.append(str(100 + idx - 8))
        else:
            codes.append(f"48;5;{idx}")

    if not codes:
        return text

    return f"\033[{';'.join(codes)}m{text}\033[0m"


def screen_to_ansi(contents) -> str:
    """Convert iTerm ScreenContents to ANSI-coded string for xterm.js."""
    lines = []
    for i in range(contents.number_of_lines):
        line = contents.line(i)
        raw_text = line.string

        # Build styled line by grouping consecutive chars with same style
        result = []
        j = 0
        while j < len(raw_text):
            char = raw_text[j]
            if char == '\x00':
                result.append(' ')
                j += 1
                continue

            try:
                style = line.style_at(j)
            except Exception:
                result.append(char)
                j += 1
                continue

            # Group consecutive chars with same style
            group = char
            k = j + 1
            while k < len(raw_text):
                next_char = raw_text[k]
                if next_char == '\x00':
                    break
                try:
                    next_style = line.style_at(k)
                    if (next_style.bold != style.bold or
                        next_style.italic != style.italic or
                        next_style.fg_color.is_rgb != style.fg_color.is_rgb or
                        next_style.fg_color.is_standard != style.fg_color.is_standard):
                        break
                    if style.fg_color.is_rgb and next_style.fg_color.is_rgb:
                        if style.fg_color.rgb != next_style.fg_color.rgb:
                            break
                    if style.fg_color.is_standard and next_style.fg_color.is_standard:
                        if style.fg_color.standard != next_style.fg_color.standard:
                            break
                except Exception:
                    break
                group += next_char
                k += 1

            result.append(style_to_ansi(style, group))
            j = k

        # Strip trailing spaces
        line_text = ''.join(result).rstrip()
        lines.append(line_text)

    # Remove trailing empty lines
    while lines and not lines[-1]:
        lines.pop()

    return '\r\n'.join(lines)


class Bridge:
    def __init__(self, port: int, session_id: Optional[str] = None):
        self.port = port
        self.session_id = session_id
        self.token = generate_token()
        self.lan_ip = get_lan_ip()
        self.active_ws = None
        self.iterm_session = None
        self.running = False

    async def find_session(self, app):
        """Find the target iTerm session."""
        if self.session_id:
            for window in app.terminal_windows:
                for tab in window.tabs:
                    for session in tab.sessions:
                        if session.session_id == self.session_id:
                            return session
            return None

        # List all sessions, let user pick or auto-select
        sessions = []
        for window in app.terminal_windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    sessions.append(session)

        if not sessions:
            return None
        if len(sessions) == 1:
            return sessions[0]

        # Print sessions for user to pick
        print("\nMultiple sessions found:")
        for i, s in enumerate(sessions):
            print(f"  {i+1}. {s.name} ({s.session_id})")
        print(f"\nRe-run with: python bridge.py --session <SESSION_ID>")
        print(f"Using first session: {sessions[0].name}")
        return sessions[0]

    async def handle_ws(self, ws):
        """Handle a phone WebSocket connection."""
        # Auth check
        path = ws.request.path if hasattr(ws.request, 'path') else ws.path
        if f"token={self.token}" not in (path or ""):
            await ws.close(4001, "Unauthorized")
            return

        if self.active_ws is not None:
            await ws.close(4009, "Another client connected")
            return

        self.active_ws = ws
        print(f"Phone connected")

        try:
            # Send initial screen content
            contents = await self.iterm_session.async_get_screen_contents()
            ansi_text = screen_to_ansi(contents)
            await ws.send(json.dumps({"type": "screen", "data": ansi_text}))

            # Start streaming in background
            stream_task = asyncio.create_task(self.stream_to_phone(ws))

            # Handle input from phone
            async for message in ws:
                if isinstance(message, bytes):
                    # Binary = keystrokes
                    text = message.decode("utf-8")
                    await self.iterm_session.async_send_text(text)
                else:
                    # Text = control message (ignore for now)
                    pass

        except websockets.ConnectionClosed:
            pass
        finally:
            stream_task.cancel()
            self.active_ws = None
            print("Phone disconnected")

    async def stream_to_phone(self, ws):
        """Stream screen updates to the phone."""
        try:
            async with self.iterm_session.get_screen_streamer(want_contents=True) as streamer:
                while True:
                    try:
                        contents = await asyncio.wait_for(streamer.async_get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        # Send a ping to keep connection alive
                        continue

                    if ws.closed:
                        break

                    ansi_text = screen_to_ansi(contents)
                    try:
                        await ws.send(json.dumps({"type": "screen", "data": ansi_text}))
                    except websockets.ConnectionClosed:
                        break
        except asyncio.CancelledError:
            pass

    async def run_bridge(self, connection):
        """Main bridge logic — runs inside iTerm2 API context."""
        app = await iterm2.async_get_app(connection)
        self.iterm_session = await self.find_session(app)

        if not self.iterm_session:
            print("No iTerm session found!")
            return

        print(f"Attached to: {self.iterm_session.name}")

        if not self.lan_ip:
            print("Could not detect LAN IP!")
            return

        # Start WebSocket server
        async def ws_handler(ws):
            await self.handle_ws(ws)

        server = await ws_serve(ws_handler, self.lan_ip, self.port)

        print(f"""
╔══════════════════════════════════════════════════════╗
║           Claude Code Terminal Mirror                ║
║                (iTerm2 API mode)                     ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  URL:   http://{(self.lan_ip + ':' + str(self.port)).ljust(37)}║
║  Token: {self.token.ljust(44)}║
║                                                      ║
║  Open the URL on your phone and enter the token.     ║
║  Your laptop terminal is NOT affected.               ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
""")

        self.running = True
        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            pass
        finally:
            server.close()

    def start(self):
        """Entry point."""
        iterm2.run_until_complete(self.run_bridge)


# --- Simple HTTP + WS server ---
# websockets doesn't serve HTTP, so we need a thin wrapper
# to serve index.html on GET / and upgrade to WS on /ws

import http.server
import threading


class HTTPHandler(http.server.BaseHTTPRequestHandler):
    bridge = None

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html_path = os.path.join(os.path.dirname(__file__), "src", "ui", "iterm.html")
            with open(html_path, "r") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Silence HTTP logs


def main():
    parser = argparse.ArgumentParser(description="Terminal Mirror — iTerm2 API")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--http-port", type=int, default=8801)
    parser.add_argument("--session", type=str, default=None)
    args = parser.parse_args()

    bridge = Bridge(port=args.port, session_id=args.session)

    # Start HTTP server in a thread for serving the HTML
    HTTPHandler.bridge = bridge
    http_server = http.server.HTTPServer((bridge.lan_ip or "0.0.0.0", args.http_port), HTTPHandler)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()

    print(f"HTTP server on port {args.http_port} (for the UI)")
    bridge.start()


if __name__ == "__main__":
    main()
