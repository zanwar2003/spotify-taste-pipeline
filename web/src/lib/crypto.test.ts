import assert from "node:assert/strict";
import { test } from "node:test";
import { decrypt, encrypt } from "./crypto.ts";

const KEY = "a".repeat(64);

test("round-trips a refresh token", () => {
  const token = "AQD-refresh-token-value";
  assert.equal(decrypt(encrypt(token, KEY), KEY), token);
});

test("uses a fresh IV each time", () => {
  assert.notEqual(encrypt("same", KEY), encrypt("same", KEY));
});

test("rejects tampered ciphertext", () => {
  const raw = Buffer.from(encrypt("secret", KEY), "base64");
  raw[raw.length - 1] ^= 1;
  assert.throws(() => decrypt(raw.toString("base64"), KEY));
});

test("rejects a key of the wrong length", () => {
  assert.throws(() => encrypt("x", "abcd"));
});
