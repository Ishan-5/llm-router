import { test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs } from "../src/parse.js";

test("parses command and positionals", () => {
  const p = parseArgs(["ask", "hello", "world"]);
  assert.equal(p.command, "ask");
  assert.deepEqual(p.positionals, ["hello", "world"]);
});

test("parses --flag value and --flag=value", () => {
  const p1 = parseArgs(["ask", "--tier", "frontier", "q"]);
  assert.equal(p1.flags["tier"], "frontier");
  const p2 = parseArgs(["ask", "--tier=mid", "q"]);
  assert.equal(p2.flags["tier"], "mid");
});

test("parses boolean flags", () => {
  const p = parseArgs(["ask", "--json", "--bypass-cache", "q"]);
  assert.equal(p.flags["json"], true);
  assert.equal(p.flags["bypass-cache"], true);
});

test("normalizes underscore flags", () => {
  const p = parseArgs(["ask", "--bypass_cache", "q"]);
  assert.equal(p.flags["bypass-cache"], true);
});

test("unknown long flag is a boolean present", () => {
  const p = parseArgs(["ask", "--whatever", "q"]);
  assert.equal(p.flags["whatever"], true);
  assert.deepEqual(p.positionals, ["q"]);
});

test("short flag", () => {
  const p = parseArgs(["ask", "-q", "hi"]);
  assert.equal(p.flags["q"], true);
});

test("missing value errors", () => {
  assert.throws(() => parseArgs(["ask", "--tier"]), /Missing value for --tier/);
});

test("default command is help", () => {
  const p = parseArgs([]);
  assert.equal(p.command, "help");
});