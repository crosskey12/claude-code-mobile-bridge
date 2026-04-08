import { parseArgs } from "node:util";
import { getLanIP } from "./network.ts";
import { generateToken, createAuthValidator } from "./auth.ts";
import { TmuxTerminal } from "./terminal.ts";
import { createServer } from "./server.ts";

const { values } = parseArgs({
  options: {
    port: { type: "string", default: "8800" },
    session: { type: "string", short: "s" },
    "no-resize": { type: "boolean", default: false },
  },
  strict: false,
});

const port = parseInt(values.port as string, 10);

// Resolve tmux session
let sessionName = values.session as string | undefined;
if (!sessionName) {
  const sessions = TmuxTerminal.listSessions();
  if (sessions.length === 0) {
    console.error("No tmux sessions found. Start one first:\n  tmux new -s claude");
    process.exit(1);
  }
  if (sessions.length === 1) {
    sessionName = sessions[0];
  } else {
    console.error("Multiple tmux sessions found. Pick one with --session:\n");
    for (const s of sessions) {
      console.error(`  npm start -- --session ${s}`);
    }
    process.exit(1);
  }
}

// Validate session exists
if (!TmuxTerminal.sessionExists(sessionName)) {
  console.error(`tmux session "${sessionName}" not found.\nStart it first: tmux new -s ${sessionName}`);
  process.exit(1);
}

const lanIP = getLanIP();
if (!lanIP) {
  console.error("Could not detect a LAN IP address. Are you connected to WiFi?");
  process.exit(1);
}

const token = generateToken();
const authValidator = createAuthValidator(token);
const terminal = new TmuxTerminal(sessionName);
terminal.attach();

const server = createServer({ host: lanIP, port, authValidator, terminal });
await server.start();

const urlStr = `http://${lanIP}:${port}`;

console.log(`
╔══════════════════════════════════════════════════════╗
║           Claude Code Terminal Mirror                ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  URL:   ${urlStr.padEnd(44)}║
║  Token: ${token.padEnd(44)}║
║  tmux:  ${sessionName.padEnd(44)}║
║                                                      ║
║  Open the URL on your phone and enter the token.     ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
`);

// Graceful shutdown
let shuttingDown = false;
function shutdown() {
  if (shuttingDown) {
    process.exit(1); // Force exit on second Ctrl+C
  }
  shuttingDown = true;
  console.log("\nShutting down (tmux session stays running)...");
  terminal.restoreSize();
  terminal.kill();
  server.stop().finally(() => process.exit(0));
  // Force exit after 2s if server.stop() hangs
  setTimeout(() => process.exit(0), 2000).unref();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// If tmux session ends, shut down the bridge
terminal.on("exit", () => {
  console.log("\ntmux session ended. Shutting down...");
  terminal.kill();
  server.stop().finally(() => process.exit(0));
});
