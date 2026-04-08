import { execFileSync } from "node:child_process";
import { openSync, readSync, closeSync, writeFileSync, unlinkSync } from "node:fs";
import { EventEmitter } from "node:events";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

const TMUX_PATH = "/opt/homebrew/bin/tmux";
const POLL_INTERVAL_MS = 50;

export class TmuxTerminal extends EventEmitter {
  readonly sessionName: string;
  private pipePath: string;
  private pipeFd: number | null = null;
  private pipePosition = 0;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private attached = false;

  constructor(sessionName: string) {
    super();
    this.sessionName = sessionName;
    this.pipePath = join(tmpdir(), `ccbridge-${randomUUID()}.pipe`);
  }

  static sessionExists(name: string): boolean {
    try {
      execFileSync(TMUX_PATH, ["has-session", "-t", name], { stdio: "ignore" });
      return true;
    } catch {
      return false;
    }
  }

  static listSessions(): string[] {
    try {
      const out = execFileSync(TMUX_PATH, ["list-sessions", "-F", "#{session_name}"], {
        stdio: ["ignore", "pipe", "ignore"],
      });
      return out.toString().trim().split("\n").filter(Boolean);
    } catch {
      return [];
    }
  }

  attach(): void {
    if (this.attached) throw new Error("Already attached");

    if (!TmuxTerminal.sessionExists(this.sessionName)) {
      throw new Error(
        `tmux session "${this.sessionName}" not found. Start it first: tmux new -s ${this.sessionName}`
      );
    }

    // Create the pipe output file
    writeFileSync(this.pipePath, "");

    // Start tmux pipe-pane: captures all pane output (with ANSI codes) to our file
    execFileSync(TMUX_PATH, [
      "pipe-pane", "-t", this.sessionName,
      `cat >> ${this.pipePath}`,
    ]);

    // Open file for reading
    this.pipeFd = openSync(this.pipePath, "r");
    this.pipePosition = 0;
    this.attached = true;

    // Poll the file for new data
    this.pollTimer = setInterval(() => this.readNewData(), POLL_INTERVAL_MS);
  }

  write(data: string): void {
    if (!this.attached) return;

    // Send raw keystrokes to the tmux pane using send-keys -l (literal mode)
    try {
      execFileSync(TMUX_PATH, ["send-keys", "-t", this.sessionName, "-l", data], {
        stdio: "ignore",
      });
    } catch {
      // Session might have ended
    }
  }

  sendSpecialKey(key: string): void {
    if (!this.attached) return;
    try {
      execFileSync(TMUX_PATH, ["send-keys", "-t", this.sessionName, key], {
        stdio: "ignore",
      });
    } catch {
      // Session might have ended
    }
  }

  private savedSize: { cols: number; rows: number } | null = null;

  resize(cols: number, rows: number): void {
    if (!this.attached) return;

    // Save original laptop size on first resize
    if (!this.savedSize) {
      this.savedSize = this.getPaneSize();
    }

    try {
      execFileSync(TMUX_PATH, [
        "resize-window", "-t", this.sessionName, "-x", String(cols), "-y", String(rows),
      ], { stdio: "ignore" });
    } catch {
      // resize may fail
    }
  }

  restoreSize(): void {
    if (!this.savedSize || !this.attached) return;
    try {
      execFileSync(TMUX_PATH, [
        "resize-window", "-t", this.sessionName,
        "-x", String(this.savedSize.cols), "-y", String(this.savedSize.rows),
      ], { stdio: "ignore" });
    } catch {
      // ignore
    }
    this.savedSize = null;
  }

  getPaneSize(): { cols: number; rows: number } {
    try {
      const out = execFileSync(TMUX_PATH, [
        "display-message", "-t", this.sessionName, "-p", "#{pane_width} #{pane_height}",
      ], { stdio: ["ignore", "pipe", "ignore"] });
      const [cols, rows] = out.toString().trim().split(" ").map(Number);
      return { cols: cols || 80, rows: rows || 24 };
    } catch {
      return { cols: 80, rows: 24 };
    }
  }

  captureScrollback(lines: number = 1000): string {
    try {
      const out = execFileSync(TMUX_PATH, [
        "capture-pane", "-t", this.sessionName, "-p", "-e", "-S", `-${lines}`,
      ], {
        stdio: ["ignore", "pipe", "ignore"],
      });
      return out.toString();
    } catch {
      return "";
    }
  }

  isAttached(): boolean {
    return this.attached;
  }

  kill(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }

    // Stop pipe-pane
    if (this.attached) {
      try {
        execFileSync(TMUX_PATH, ["pipe-pane", "-t", this.sessionName], { stdio: "ignore" });
      } catch {
        // Session might already be gone
      }
    }

    if (this.pipeFd !== null) {
      closeSync(this.pipeFd);
      this.pipeFd = null;
    }

    // Clean up temp file
    try {
      unlinkSync(this.pipePath);
    } catch {
      // file might not exist
    }

    this.attached = false;
  }

  private readNewData(): void {
    if (this.pipeFd === null) return;

    const buf = Buffer.alloc(16384);
    try {
      const bytesRead = readSync(this.pipeFd, buf, 0, 16384, this.pipePosition);
      if (bytesRead > 0) {
        this.pipePosition += bytesRead;
        this.emit("data", buf.toString("utf-8", 0, bytesRead));
      }
    } catch {
      // File read error — session may have ended
      this.emit("exit", 1);
      this.kill();
    }
  }
}
