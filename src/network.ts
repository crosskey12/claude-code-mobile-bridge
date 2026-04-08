import os from "node:os";

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
