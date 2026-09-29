import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { requireEnv } from "./env.ts";

/** AES-256-GCM. Output format: base64(iv | authTag | ciphertext). */
function key(hex?: string): Buffer {
  const k = Buffer.from(hex ?? requireEnv("TOKEN_ENCRYPTION_KEY"), "hex");
  if (k.length !== 32) throw new Error("TOKEN_ENCRYPTION_KEY must be 32 bytes (64 hex chars)");
  return k;
}

export function encrypt(plaintext: string, keyHex?: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(keyHex), iv);
  const body = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), body]).toString("base64");
}

export function decrypt(encoded: string, keyHex?: string): string {
  const raw = Buffer.from(encoded, "base64");
  const decipher = createDecipheriv("aes-256-gcm", key(keyHex), raw.subarray(0, 12));
  decipher.setAuthTag(raw.subarray(12, 28));
  return Buffer.concat([decipher.update(raw.subarray(28)), decipher.final()]).toString("utf8");
}
