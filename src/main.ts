import { parseArgs } from "node:util";
import { getLanIP, getLocalHostname } from "./network.ts";
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

// Bind to 0.0.0.0 so both IP and hostname connections work
const server = createServer({ host: "0.0.0.0", port, authValidator, terminal });
await server.start();

const hostname = getLocalHostname();
const ipUrl = `http://${lanIP}:${port}`;
const hostUrl = hostname ? `http://${hostname}:${port}` : null;

const dim = (s: string) => `\x1b[2m${s}\x1b[0m`;
const bold = (s: string) => `\x1b[1m${s}\x1b[0m`;
const cyan = (s: string) => `\x1b[36m${s}\x1b[0m`;
const green = (s: string) => `\x1b[32m${s}\x1b[0m`;
const yellow = (s: string) => `\x1b[33m${s}\x1b[0m`;
const magenta = (s: string) => `\x1b[35m${s}\x1b[0m`;

console.log(`
  ${bold(cyan("Claude Code Terminal Mirror"))}
  ${dim("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")}

  ${dim("URL")}     ${green(ipUrl)}${hostUrl ? `\n  ${dim(" ")}       ${green(hostUrl)}` : ""}
  ${dim("Token")}   ${yellow(token)}
  ${dim("tmux")}    ${magenta(sessionName)}

  Open the URL on your phone and enter the token.${hostUrl ? `\n  ${dim(".local works on iOS. Android? lol good luck.")}` : ""}
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
