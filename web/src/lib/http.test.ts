import assert from "node:assert/strict";
import { test } from "node:test";
import { isUuid, parseMinutes, sameOrigin } from "./http.ts";

test("isUuid accepts UUIDs and rejects path tricks", () => {
  assert.equal(isUuid("3f1d2c4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f"), true);
  for (const bad of ["", "abc", "../../etc/passwd", "3f1d2c4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f/../x"]) {
    assert.equal(isUuid(bad), false, bad);
  }
});

test("sameOrigin requires Origin to match the Host the request was sent to", () => {
  assert.equal(sameOrigin("http://127.0.0.1:3000", "127.0.0.1:3000"), true);
  assert.equal(sameOrigin("https://app.example.com", "app.example.com"), true);
  assert.equal(sameOrigin("https://evil.example", "127.0.0.1:3000"), false);
  assert.equal(sameOrigin("http://127.0.0.1:4000", "127.0.0.1:3000"), false); // other port
  assert.equal(sameOrigin("http://127.0.0.1:3000.evil.example", "127.0.0.1:3000"), false);
});

test("sameOrigin refuses missing, opaque and malformed origins", () => {
  assert.equal(sameOrigin(null, "127.0.0.1:3000"), false);
  assert.equal(sameOrigin("http://127.0.0.1:3000", null), false);
  assert.equal(sameOrigin("null", "null"), false);
  assert.equal(sameOrigin("not a url", "not a url"), false);
  assert.equal(sameOrigin("file:///etc/passwd", ""), false);
});

test("parseMinutes understands common phrasings", () => {
  assert.equal(parseMinutes("45"), 45);
  assert.equal(parseMinutes("90 min"), 90);
  assert.equal(parseMinutes("1.5 hours"), 90);
  assert.equal(parseMinutes("2h"), 120);
  assert.equal(parseMinutes(" 30 minutes "), 30);
});

test("parseMinutes rejects nonsense and out-of-range values", () => {
  for (const bad of ["", "soon", "0", "-5", "481", "9 days", "1e3"]) {
    assert.equal(parseMinutes(bad), null, bad);
  }
});
