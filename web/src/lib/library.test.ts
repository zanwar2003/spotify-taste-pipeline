import assert from "node:assert/strict";
import { test } from "node:test";
import { buildLibraryQuery, escapeLike, parseSort, parseStatus } from "./library.ts";

test("unknown sort falls back to newest", () => {
  assert.equal(parseSort("'; DROP TABLE playlists; --"), "newest");
  assert.equal(parseSort(undefined), "newest");
  assert.equal(parseSort("name"), "name");
});

test("unknown status is ignored", () => {
  assert.equal(parseStatus("bogus"), null);
  assert.equal(parseStatus("exported"), "exported");
});

test("LIKE wildcards are escaped", () => {
  assert.equal(escapeLike("100%_done\\"), "100\\%\\_done\\\\");
});

test("user input is passed as parameters, never interpolated", () => {
  const { sql, params } = buildLibraryQuery("newest", "draft", "x'; DROP TABLE users; --");
  assert.ok(!sql.includes("DROP TABLE"));
  assert.deepEqual(params, ["draft", "x'; DROP TABLE users; --"]);
});
