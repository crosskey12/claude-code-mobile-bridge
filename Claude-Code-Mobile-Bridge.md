# Claude Code Mobile Bridge

## Core Idea

A lightweight local app that bridges Claude Code (running in the terminal on your machine) with your phone over the same WiFi network — letting you send prompts and read responses from your phone without any traffic ever hitting the internet.

Your phone connects to your machine's local IP. The app relays input to Claude Code's terminal session and streams output back. Pure local routing.

---

## The Problem

Claude Code is a powerful CLI tool, but it's locked to your keyboard and terminal. Sometimes you want to:

- Fire off a prompt from the couch while your machine works in the background
- Review Claude Code's output on your phone while away from your desk
- Approve or deny tool calls from your phone
- Monitor a long-running Claude Code session without staying at the terminal

There's no way to interact with a running Claude Code session from another device today.

---

## How It Works

```
┌──────────────┐        WiFi (local IP)        ┌──────────────┐
│              │  ◄──────────────────────────►  │              │
│    Phone     │    never hits the internet     │   Your Mac   │
│   (browser)  │                                │              │
│              │         HTTP / WebSocket        │  Bridge App  │
└──────────────┘        e.g. 192.168.1.42:8800  │      ↕       │
                                                │ Claude Code  │
                                                │  (terminal)  │
                                                └──────────────┘
```

### Components

**1. Bridge Server (runs on your machine)**
- A lightweight local server (Node.js or Python)
- Spawns or attaches to a Claude Code terminal session
- Exposes a WebSocket + REST API on the local network
- Relays input from phone → Claude Code stdin
- Streams output from Claude Code stdout → phone
- Serves a mobile-friendly web UI

**2. Mobile Web UI (runs in phone browser)**
- No app install needed — just open `http://<your-ip>:8800` in Safari/Chrome
- Chat-style interface showing Claude Code's conversation
- Text input for sending prompts
- Action buttons for approving/denying tool calls
- Real-time streaming of Claude Code's output via WebSocket

**3. Terminal Session Manager**
- Manages the Claude Code process (start, attach, detach)
- Uses a PTY (pseudo-terminal) to interact with Claude Code programmatically
- Handles ANSI escape codes — strips or converts for clean mobile display
- Buffers conversation history so the phone can load context on connect

---

## Key Design Decisions

### Local-only routing
- The bridge server binds to the machine's local network interface (e.g. `192.168.1.x`)
- Traffic between phone and machine travels through the WiFi router's local routing table
- **No packets leave the local network** — no DNS, no internet gateway, no cloud
- This is how any device on the same LAN talks to another — standard TCP/IP

### No app install on phone
- The mobile UI is a web page served by the bridge server
- Works on any phone with a browser — iOS Safari, Android Chrome
- Could be "installed" as a PWA (Add to Home Screen) for app-like experience

### Terminal interaction model
- Claude Code is an interactive CLI — it expects a TTY
- The bridge uses a PTY (via `node-pty` or Python `pty` module) to simulate a terminal
- This captures rich output including formatted text, tool call prompts, etc.
- ANSI codes are parsed and either stripped (for plain text) or converted to HTML (for styled display)

---

## Interface

### Connecting
1. Start the bridge: `ccbridge start` (or similar)
2. It prints: `Bridge running at http://192.168.1.42:8800`
3. Open that URL on your phone
4. You see Claude Code's current conversation and can start typing

### Mobile UI Features
- **Chat view** — scrollable conversation with Claude Code's output
- **Input bar** — type prompts, send with enter
- **Tool call cards** — when Claude Code asks for permission, show approve/deny buttons
- **Session indicator** — shows connection status, current working directory
- **Reconnect** — if phone disconnects, reconnect and catch up from buffer

### CLI Commands

| Command | Description |
|---|---|
| `ccbridge start` | Start bridge server + new Claude Code session |
| `ccbridge attach` | Attach bridge to an existing Claude Code session |
| `ccbridge status` | Show running sessions and connected devices |
| `ccbridge stop` | Stop the bridge server |

---

## Security Model

| Control | Specification |
|---|---|
| Network boundary | Local WiFi only — server binds to LAN interface, not `0.0.0.0` |
| Authentication | Required — short-lived token displayed on terminal at start, enter on phone to connect |
| Encryption | Optional TLS with self-signed cert for LAN (prevents WiFi sniffing) |
| Session control | Only one active phone connection at a time (configurable) |
| No telemetry | Zero outbound connections |

---

## Technical Considerations

### PTY management
- `node-pty` (Node.js) or `pexpect`/`pty` (Python) for terminal emulation
- Need to handle Claude Code's rich output: markdown, code blocks, progress indicators
- Buffer size management — keep last N lines of conversation for phone reconnection

### ANSI parsing
- Claude Code outputs styled terminal text (colors, bold, etc.)
- Options: strip all ANSI (simple), or convert to HTML spans (richer mobile experience)
- Libraries: `ansi-to-html` (Node.js), `ansi2html` (Python)

### Latency
- Local WiFi round trip is typically <5ms
- WebSocket keeps connection open — no HTTP overhead per message
- Streaming output feels real-time

### Claude Code interaction model
- Claude Code uses stdin/stdout for conversation
- Tool call approvals appear as prompts waiting for input
- The bridge needs to detect these prompts and surface them as actionable UI elements on the phone

---

## MVP Scope

- Bridge server with PTY-based Claude Code session management
- WebSocket streaming of output to phone
- Mobile web UI with chat view and text input
- Token-based auth on connect
- Basic tool call approve/deny buttons

## Post-MVP

- Multiple concurrent sessions
- Session history / persistence across bridge restarts
- Voice input on phone
- File preview (when Claude Code reads/writes files, show snippets on phone)
- Notification when Claude Code needs input (push via service worker)

---

## How This Relates to AIX

This is a **separate project** from AIX, but shares the same philosophy:
- Local-first, no cloud
- WiFi LAN access from phone
- Developer tool that extends your terminal's reach

A future integration point: the bridge could pipe Claude Code sessions into AIX as Runs — capturing every prompt, response, and tool call as structured, diffable data.

---

*Draft — v0.1*
