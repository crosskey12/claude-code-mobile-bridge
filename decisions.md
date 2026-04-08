# Decisions

## Terminal mirror approach (chosen)

**Implemented:** tmux-based terminal mirroring. The bridge attaches to a running tmux session using `tmux pipe-pane` (for streaming output) and `tmux send-keys -l` (for input). Phone runs xterm.js to render the terminal. Both laptop and phone see and interact with the same session.

**Why tmux:** Real-time streaming of terminal output with full ANSI codes. Both devices share the same session. Industry standard multiplexer.

**Why not node-pty:** `node-pty` failed with `posix_spawnp` errors (sandbox/Node v25 compatibility). The `pipe-pane` + `send-keys` approach works without native addons and has zero dependencies beyond `ws`.

**Downside of tmux approach:** Requires the user to run inside tmux. Adds a setup step. Not everyone uses tmux.

## iTerm2 Python API — not explored, should be tried

**What it is:** iTerm2 has a built-in Python scripting API with a daemon running at `~/Library/Application Support/iTerm2/iterm2-daemon-1.socket`. It uses JSON-RPC over a Unix domain socket and supports:

- **Event monitoring** — subscribe to session changes, custom control sequences via `CustomControlSequenceMonitor`
- **Async/await** — native async Python API
- **Session access** — read content, write text, create windows/tabs
- **Daemon mode** — long-running scripts that stay connected to iTerm (template at `/Applications/iTerm.app/Contents/Resources/template_basic_daemon.py`)
- **Protocol** — framing implementation at `/Applications/iTerm.app/Contents/Resources/framer.py`

**Why this might be better than tmux:**
- No tmux required — works with any iTerm session directly
- Could potentially **stream** output via event subscriptions (not polling)
- Tighter integration — iTerm knows about sessions, tabs, windows natively
- The user already uses iTerm, so zero setup

**Why it wasn't explored:**
- Went with tmux because it was the "known" approach with clear terminal I/O semantics
- Didn't investigate whether the Python API can stream raw terminal output with ANSI codes (vs just `get contents` which strips them)
- Would require Python as a dependency (or a Python subprocess managed by the Node bridge)

**Key unknowns to resolve:**
1. Can the Python API subscribe to real-time session output (with ANSI codes), or is it still polling `get contents`?
2. What's the latency of the daemon socket communication?
3. Can `write text` handle raw control characters (Ctrl+C, escape sequences) reliably?
4. Could the bridge be rewritten entirely in Python using the iterm2 API + a WebSocket server (aiohttp/websockets)?

**TODO:** Prototype a simple Python script that connects to the iTerm daemon, subscribes to a session's output stream, and prints it. If it streams with ANSI codes, this could replace the tmux approach entirely and eliminate the tmux requirement.

## iTerm AppleScript API — explored, insufficient

`get contents` is polling-based, strips ANSI codes (no colors), and can't stream. `write text` works for input. Could be a low-fidelity fallback but not a primary approach. The Python API is strictly more capable.

## Chat bridge approach (v1, replaced)

The original v1 spawned `claude -p --output-format stream-json` per message and relayed structured JSON to a custom chat UI. This created a **separate Claude session** invisible to the terminal. Replaced because the user wants phone = terminal mirror, not a parallel session.

The v1 code is preserved in git history if needed.
