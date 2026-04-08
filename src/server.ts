import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer, WebSocket } from "ws";
import type { TmuxTerminal } from "./terminal.ts";
import type { ControlMessage } from "./types.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export interface ServerOptions {
  host: string;
  port: number;
  authValidator: { validate(token: string): boolean };
  terminal: TmuxTerminal;
}

export function createServer(options: ServerOptions) {
  const { host, port, authValidator, terminal } = options;

  const indexHtml = fs.readFileSync(path.join(__dirname, "ui", "index.html"), "utf-8");
  const manifest = fs.readFileSync(path.join(__dirname, "ui", "manifest.json"), "utf-8");

  const httpServer = http.createServer((req, res) => {
    if (req.url === "/" || req.url === "/index.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(indexHtml);
    } else if (req.url === "/manifest.json") {
      res.writeHead(200, { "Content-Type": "application/manifest+json" });
      res.end(manifest);
    } else if (req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        ok: true,
        attached: terminal.isAttached(),
        session: terminal.sessionName,
      }));
    } else {
      res.writeHead(404);
      res.end("Not Found");
    }
  });

  const wss = new WebSocketServer({ noServer: true });
  let activeClient: WebSocket | null = null;

  httpServer.on("upgrade", (req, socket, head) => {
    const url = new URL(req.url!, `http://${req.headers.host}`);
    const token = url.searchParams.get("token");

    if (!token || !authValidator.validate(token)) {
      socket.write("HTTP/1.1 401 Unauthorized\r\n\r\n");
      socket.destroy();
      return;
    }

    if (activeClient && activeClient.readyState === WebSocket.OPEN) {
      socket.write("HTTP/1.1 409 Conflict\r\n\r\n");
      socket.destroy();
      return;
    }

    wss.handleUpgrade(req, socket, head, (ws) => {
      activeClient = ws;
      wss.emit("connection", ws, req);
    });
  });

  // Track the live relay handler so we can clean up on disconnect
  let liveHandler: ((data: string) => void) | null = null;

  wss.on("connection", (ws: WebSocket) => {
    ws.binaryType = "arraybuffer";

    // Buffer live output until we're ready to stream
    const buffer: Buffer[] = [];
    const bufferHandler = (data: string) => {
      buffer.push(Buffer.from(data, "utf-8"));
    };
    terminal.on("data", bufferHandler);

    // Send pane dimensions so phone can calculate its size
    const paneSize = terminal.getPaneSize();
    ws.send(JSON.stringify({ type: "pane_size", cols: paneSize.cols, rows: paneSize.rows }));

    // Wait for phone's first resize before sending scrollback.
    // The phone calculates its cols/rows, sends resize, THEN we
    // capture scrollback at the correct (phone) width.
    let scrollbackSent = false;

    function sendScrollbackAndStartRelay() {
      if (scrollbackSent) return;
      scrollbackSent = true;

      // Small delay to let tmux redraw at the new size
      setTimeout(() => {
        const scrollback = terminal.captureScrollback(1000);
        ws.send(JSON.stringify({ type: "scrollback", data: scrollback }));

        // Flush buffered live data
        terminal.removeListener("data", bufferHandler);
        for (const chunk of buffer) {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(chunk);
          }
        }

        // Switch to live relay
        liveHandler = (data: string) => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(Buffer.from(data, "utf-8"));
          }
        };
        terminal.on("data", liveHandler);
      }, 300);
    }

    // Handle incoming messages from phone
    ws.on("message", (data, isBinary) => {
      if (isBinary) {
        // Binary = raw keystrokes from xterm.js
        const str = Buffer.isBuffer(data) ? data.toString("utf-8") : Buffer.from(data as ArrayBuffer).toString("utf-8");
        terminal.write(str);
      } else {
        // Text = control message (JSON)
        try {
          const msg: ControlMessage = JSON.parse(data.toString());
          if (msg.type === "resize") {
            terminal.resize(msg.cols, msg.rows);
            // First resize triggers scrollback capture
            sendScrollbackAndStartRelay();
          }
        } catch {
          // ignore malformed control messages
        }
      }
    });

    // Fallback: if phone never sends resize (e.g. desktop browser), send scrollback after 2s
    setTimeout(() => sendScrollbackAndStartRelay(), 2000);

    ws.on("close", () => {
      // Restore laptop terminal size
      terminal.restoreSize();

      if (liveHandler) {
        terminal.removeListener("data", liveHandler);
        liveHandler = null;
      }
      if (activeClient === ws) {
        activeClient = null;
      }
    });
  });

  // Send error to active client if terminal exits
  terminal.on("exit", (code: number) => {
    if (activeClient && activeClient.readyState === WebSocket.OPEN) {
      const msg: ControlMessage = { type: "error", message: `tmux session ended (exit code: ${code})` };
      activeClient.send(JSON.stringify(msg));
    }
  });

  return {
    start(): Promise<void> {
      return new Promise((resolve) => {
        httpServer.listen(port, host, () => resolve());
      });
    },
    stop(): Promise<void> {
      return new Promise((resolve) => {
        for (const client of wss.clients) {
          client.close();
        }
        httpServer.close(() => resolve());
      });
    },
  };
}
