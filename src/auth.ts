import crypto from "node:crypto";

const ADJECTIVES = [
  "brave", "calm", "dark", "eager", "fair", "glad", "happy", "keen",
  "lively", "mellow", "noble", "proud", "quick", "rapid", "sharp",
  "swift", "tall", "vast", "warm", "wise", "bold", "cool", "deep",
  "fast", "gentle", "kind", "lucky", "neat", "quiet", "silent",
];

const NOUNS = [
  "river", "storm", "cloud", "flame", "frost", "grove", "hawk",
  "lake", "maple", "oak", "peak", "rain", "sage", "stone", "tiger",
  "wave", "wolf", "cedar", "dawn", "eagle", "falcon", "harbor",
  "jade", "marsh", "panda", "ridge", "spark", "trail", "vine", "willow",
];

function pick(arr: string[]): string {
  const idx = crypto.randomInt(arr.length);
  return arr[idx];
}

export function generateToken(): string {
  return `${pick(ADJECTIVES)}_${pick(NOUNS)}`;
}

export function createAuthValidator(token: string) {
  return {
    validate(candidate: string): boolean {
      if (candidate.length !== token.length) return false;
      return crypto.timingSafeEqual(
        Buffer.from(candidate),
        Buffer.from(token)
      );
    },
  };
}
