# Claude Code Mobile Bridge

Mirror your Claude Code terminal session to your phone over local WiFi. No internet, no app install, no cloud.

```
Phone (Safari/Chrome)  <--WiFi-->  Bridge Server  <-->  tmux (Claude Code)
     xterm.js UI              WebSocket + HTTP        pipe-pane + polling
```

## Why

Claude Code is locked to your keyboard. This lets you:

- Send prompts from the couch while your Mac works
- Approve/deny tool calls from your phone
- Monitor long-running sessions without sitting at the desk
- Review output on the go

Everything stays on your local network. Zero packets leave your WiFi.

## Demo

<!-- TODO: Add a GIF/screenshot here -->

## Quick Start

### Prerequisites

- **Node.js 23+** (uses native TypeScript via `--experimental-strip-types`)
- **tmux** (`brew install tmux`)
- Mac and phone on the **same WiFi network**

### Install

```bash
git clone https://github.com/crosskey12/claude-code-mobile-bridge.git
cd claude-code-mobile-bridge
npm install
```

### Run

**1. Start Claude Code inside tmux:**

```bash
tmux new -s claude
claude
```

**2. Open a new terminal and start the bridge:**

```bash
npm start -- --session claude
```

**3. Open the URL on your phone and enter the token.**

The bridge prints something like:

```
Claude Code Terminal Mirror
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL     http://192.168.1.42:8800
        http://yourhost.local:8800
Token   brave_storm
tmux    claude
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--session <name>` | tmux session to attach to | auto-detect |
| `--port <number>` | Port to listen on | `8800` |

### Dev mode (auto-reload)

```bash
npm run dev -- --session claude
```

## Features

### Two-Row Toolbar
- **Nav row:** Arrow keys (hold-to-repeat), Ctrl, Enter, Esc
- **Action row:** Exit, Yes/Always/No (for Claude permission prompts), C-c, C-z, C-d

### Tap-to-Move Cursor
Tap anywhere on the current line to move the cursor there. No more mashing arrow keys.

### Claude Permission Buttons
When Claude asks for permission, tap:
- **Yes** - approve (sends `1`)
- **Always** - approve and don't ask again (sends `2`)
- **No** - deny (sends `3`)

### Other
- Real-time terminal streaming with full ANSI color support
- Touch scrolling with momentum physics
- Auto-reconnect with exponential backoff
- Auto-shrink font to guarantee 80-column minimum
- PWA installable (Add to Home Screen)
- `.local` hostname support (iOS)

## Architecture

```
src/
  main.ts          Entry point, CLI args, orchestration
  terminal.ts      TmuxTerminal — pipe-pane capture + send-keys input
  server.ts        HTTP + WebSocket server, connection relay
  auth.ts          Token generation + timing-safe validation
  network.ts       LAN IP + hostname detection
  types.ts         WebSocket message types
  ui/
    index.html     Mobile web UI (xterm.js, toolbar, touch handling)
    manifest.json  PWA manifest
```

**How it works:**

1. Bridge attaches to your tmux session via `tmux pipe-pane` (captures output to a temp file)
2. Polls the pipe file every 50ms for new data
3. Streams terminal output to the phone as binary WebSocket frames
4. Phone keystrokes are sent back as binary frames
5. Bridge injects them into tmux via `tmux send-keys -l`

Both devices see and interact with the same session.

## Security

| | |
|---|---|
| **Network** | Local WiFi only. Server binds to `0.0.0.0` but is only accessible on your LAN. |
| **Auth** | Memorable token (`brave_storm`) displayed at startup. Timing-safe comparison. |
| **Clients** | Single phone connection at a time (enforced). |
| **Data** | No telemetry, no outbound connections, no cloud. |

## Known Limitations

- Requires tmux (not a universal terminal)
- Single client only (concurrent connections rejected)
- When the phone is connected, tmux resizes to phone dimensions. Old scrollback text stays wrapped at the narrow width after disconnect. This is a tmux limitation — it doesn't reflow text.
- `.local` hostname works on iOS but not Android (mDNS limitation)
- Tap-to-cursor only works horizontally on the same line

## Tech Stack

- **Backend:** TypeScript on Node.js 23+ (zero build step)
- **Frontend:** Vanilla JS + xterm.js v6 (no framework)
- **Dependencies:** Just `ws` (WebSocket library)

## Contributing

Contributions welcome! Here's how:

1. Fork the repo
2. Create a branch (`git checkout -b my-feature`)
3. Make your changes
4. Test on an actual phone (this is a mobile-first project)
5. Commit (`git commit -m "Add my feature"`)
6. Push (`git push origin my-feature`)
7. Open a Pull Request

### Ideas for Contributions

- **TLS support** - HTTPS/WSS for encrypted local connections
- **Multi-client** - Allow multiple phones to connect simultaneously
- **Voice input** - Speech-to-text on the phone
- **Notifications** - Push notification when Claude needs input
- **File preview** - Show file contents when Claude reads/writes
- **Better scrollback** - Solve the tmux reflow issue on disconnect
- **node-pty backend** - Alternative to tmux for users who don't want tmux
- **iTerm2 integration** - Use iTerm's Python API instead of tmux

### Development

```bash
# Install dependencies
npm install

# Run in dev mode (auto-reload on file changes)
npm run dev -- --session claude

# Type-check
npx tsc --noEmit
```

## License

MIT
