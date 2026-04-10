import os from "node:os";
import { execFileSync } from "node:child_process";

export function getLocalHostname(): string | null {
  try {
    // macOS: scutil gives the Bonjour hostname
    const name = execFileSync("scutil", ["--get", "LocalHostName"], {
      encoding: "utf-8",
    }).trim();
    return name ? `${name}.local` : null;
  } catch {
    return null;
  }
}

export function getLanIP(): string | null {
  const interfaces = os.networkInterfaces();
  for (const addrs of Object.values(interfaces)) {
    if (!addrs) continue;
    for (const addr of addrs) {
      if (addr.family === "IPv4" && !addr.internal) {
        if (
          addr.address.startsWith("10.") ||
          addr.address.startsWith("192.168.") ||
          addr.address.startsWith("172.")
        ) {
          return addr.address;
        }
      }
    }
  }
  return null;
}
