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
import subprocess
import argparse
from typing import Optional

import iterm2
from aiohttp import web


def get_lan_ip() -> Optional[str]:
    """Detect LAN IP address, preferring WiFi over VPN."""
    try:
        result = subprocess.run(["ifconfig"], capture_output=True, text=True)
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
    """Convert iTerm ScreenContents to ANSI-coded string for xterm.js.

    Uses cursor positioning to overwrite the screen in-place,
    so xterm.js doesn't need to be cleared between updates.
    """
    # Move cursor to home position and clear screen
    output = "\033[H\033[2J"

    for i in range(contents.number_of_lines):
        line = contents.line(i)
        raw_text = line.string

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

            group = char
            k = j + 1
            while k < len(raw_text):
                next_char = raw_text[k]
                if next_char == '\x00':
                    break
                try:
                    next_style = line.style_at(k)
                    same = (
                        next_style.bold == style.bold
                        and next_style.faint == style.faint
                        and next_style.italic == style.italic
                        and next_style.underline == style.underline
                        and next_style.inverse == style.inverse
                    )
                    if same:
                        # Check fg color match
                        if style.fg_color.is_rgb and next_style.fg_color.is_rgb:
                            same = style.fg_color.rgb == next_style.fg_color.rgb
                        elif style.fg_color.is_standard and next_style.fg_color.is_standard:
                            same = style.fg_color.standard == next_style.fg_color.standard
                        elif style.fg_color.is_alternate and next_style.fg_color.is_alternate:
                            same = True
                        else:
                            same = False
                    if same:
                        # Check bg color match
                        if style.bg_color.is_rgb and next_style.bg_color.is_rgb:
                            same = style.bg_color.rgb == next_style.bg_color.rgb
                        elif style.bg_color.is_standard and next_style.bg_color.is_standard:
                            same = style.bg_color.standard == next_style.bg_color.standard
                        elif style.bg_color.is_alternate and next_style.bg_color.is_alternate:
                            same = True
                        else:
                            same = False
                    if not same:
                        break
                except Exception:
                    break
                group += next_char
                k += 1

            result.append(style_to_ansi(style, group))
            j = k

        line_text = ''.join(result).rstrip()
        output += line_text
        if i < contents.number_of_lines - 1:
            output += "\r\n"

    return output


class Bridge:
    def __init__(self, port: int, session_id: Optional[str] = None):
        self.port = port
        self.session_id = session_id
        self.token = generate_token()
        self.lan_ip = get_lan_ip()
        self.active_ws: Optional[web.WebSocketResponse] = None
        self.iterm_session = None
        self.app = web.Application()
        self.app.router.add_get("/", self.handle_http)
        self.app.router.add_get("/ws", self.handle_ws)
        self.app.router.add_get("/health", self.handle_health)

    async def handle_http(self, request):
        html_path = os.path.join(os.path.dirname(__file__), "src", "ui", "iterm.html")
        with open(html_path, "r") as f:
            return web.Response(text=f.read(), content_type="text/html")

    async def handle_health(self, request):
        return web.json_response({"ok": True})

    async def handle_ws(self, request):
        # Auth check
        token = request.query.get("token", "")
        if token != self.token:
            return web.Response(status=401, text="Unauthorized")

        if self.active_ws is not None and not self.active_ws.closed:
            return web.Response(status=409, text="Another client connected")

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.active_ws = ws
        print("Phone connected")

        stream_task = None
        try:
            # Send initial screen
            contents = await self.iterm_session.async_get_screen_contents()
            ansi_text = screen_to_ansi(contents)
            await ws.send_str(json.dumps({"type": "screen", "data": ansi_text}))

            # Start streaming
            stream_task = asyncio.create_task(self.stream_to_phone(ws))

            # Handle input from phone
            async for msg in ws:
                if msg.type == web.WSMsgType.BINARY:
                    text = msg.data.decode("utf-8")
                    await self.iterm_session.async_send_text(text)
                elif msg.type == web.WSMsgType.TEXT:
                    pass  # control messages — ignore for now
                elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.ERROR):
                    break
        finally:
            if stream_task:
                stream_task.cancel()
            self.active_ws = None
            print("Phone disconnected")

        return ws

    async def stream_to_phone(self, ws: web.WebSocketResponse):
        """Stream screen updates to the phone."""
        try:
            async with self.iterm_session.get_screen_streamer(want_contents=True) as streamer:
                while not ws.closed:
                    try:
                        contents = await asyncio.wait_for(streamer.async_get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        continue

                    ansi_text = screen_to_ansi(contents)
                    try:
                        await ws.send_str(json.dumps({"type": "screen", "data": ansi_text}))
                    except (ConnectionResetError, ConnectionError):
                        break
        except asyncio.CancelledError:
            pass

    async def find_session(self, app):
        if self.session_id:
            for window in app.terminal_windows:
                for tab in window.tabs:
                    for session in tab.sessions:
                        if session.session_id == self.session_id:
                            return session
            return None

        sessions = []
        for window in app.terminal_windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    sessions.append(session)

        if not sessions:
            return None
        if len(sessions) == 1:
            return sessions[0]

        print("\nMultiple sessions found:")
        for i, s in enumerate(sessions):
            print(f"  {i+1}. {s.name} ({s.session_id})")
        print(f"\nRe-run with: python bridge.py --session <SESSION_ID>")
        print(f"Using first session: {sessions[0].name}")
        return sessions[0]

    async def run_bridge(self, connection):
        iterm_app = await iterm2.async_get_app(connection)
        self.iterm_session = await self.find_session(iterm_app)

        if not self.iterm_session:
            print("No iTerm session found!")
            return

        print(f"Attached to: {self.iterm_session.name}")

        if not self.lan_ip:
            print("Could not detect LAN IP!")
            return

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.lan_ip, self.port)
        await site.start()

        print(f"""
╔══════════════════════════════════════════════════════╗
║           Claude Code Terminal Mirror                ║
║              (iTerm2 API · no tmux)                  ║
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

        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

    def start(self):
        iterm2.run_until_complete(self.run_bridge)


def main():
    parser = argparse.ArgumentParser(description="Terminal Mirror — iTerm2 API")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--session", type=str, default=None)
    args = parser.parse_args()

    bridge = Bridge(port=args.port, session_id=args.session)
    bridge.start()


if __name__ == "__main__":
    main()
