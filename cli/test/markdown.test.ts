import { test } from "node:test";
import assert from "node:assert/strict";
import {
  createStreamState,
  flushStream,
  formatMarkdown,
  formatStreamChunk,
} from "../src/markdown.js";

test("headings become bold/underline with color, plain without", () => {
  const colored = formatMarkdown("# Big title\n\n## Section\n\ntext", { color: true });
  assert.match(colored, /\u001b\[1m\u001b\[4mBig title\u001b\[0m/);
  assert.match(colored, /\u001b\[1m\u001b\[4mSection\u001b\[0m/);

  const plain = formatMarkdown("# Big title\n\n## Section\n\ntext", { color: false });
  assert.doesNotMatch(plain, /\u001b/);
  assert.ok(plain.includes("Big title\n\nSection\n\ntext"));
});

test("bullets, ordered lists and checkboxes are humanized", () => {
  const out = formatMarkdown("- alpha\n- beta\n\n1. first\n2. second\n\n- [ ] todo\n- [x] done", {
    color: false,
  });
  assert.ok(out.includes("• alpha"));
  assert.ok(out.includes("• beta"));
  assert.ok(out.includes("1. first"));
  assert.ok(out.includes("2. second"));
  assert.ok(out.includes("☐ todo"));
  assert.ok(out.includes("☑ done"));
});

test("inline code and bold render, and markup is stripped without color", () => {
  const colored = formatMarkdown("use `ls -la` and **bold text** here", { color: true });
  assert.match(colored, /\u001b\[36mls -la\u001b\[0m/);
  assert.match(colored, /\u001b\[1mbold text\u001b\[0m/);

  const plain = formatMarkdown("use `ls -la` and **bold text** here", { color: false });
  assert.ok(plain.includes("use ls -la and bold text here"));
  assert.doesNotMatch(plain, /`/);
  assert.doesNotMatch(plain, /\*\*/);
});

test("code fences are indented and dimmed", () => {
  const colored = formatMarkdown("```js\nconst x = 1;\n```", { color: true });
  assert.match(colored, /\u001b\[2m  const x = 1;\u001b\[0m/);

  const plain = formatMarkdown("```js\nconst x = 1;\n```", { color: false });
  assert.ok(plain.includes("  const x = 1;"));
  assert.doesNotMatch(plain, /```/);
});

test("tables are column-aligned", () => {
  const md = "| name | cost |\n| --- | --- |\n| groq | $0.01 |\n| openai | $9.00 |";
  const out = formatMarkdown(md, { color: false });
  const lines = out.split("\n").map((l) => l.trim());
  assert.ok(!lines.includes("| --- | --- |"));
  assert.ok(out.includes("$0.01"));
  assert.ok(out.includes("$9.00"));
});

test("blockquotes and horizontal rules render", () => {
  const out = formatMarkdown("> stay curious\n\n---\n\nafter", { color: false });
  assert.ok(out.includes("│ stay curious"));
  assert.ok(out.includes("─".repeat(20)));
  assert.ok(out.includes("after"));
});

test("links keep the label and show the url", () => {
  const plain = formatMarkdown("see [docs](https://example.com/x)", { color: false });
  assert.ok(plain.includes("docs (https://example.com/x)"));
});

test("blank lines and paragraph breaks are preserved", () => {
  const out = formatMarkdown("para one\n\npara two", { color: false });
  assert.ok(out.includes("para one\n\npara two\n"));
});

test("streaming keeps paragraph breaks from a bare newline chunk", () => {
  const state = createStreamState();
  const a = formatStreamChunk("para one", state, { color: false });
  const b = formatStreamChunk("\n\n", state, { color: false });
  const c = formatStreamChunk("para two", state, { color: false });
  const d = flushStream(state, { color: false });
  assert.equal(a, "");
  assert.equal(b, "para one\n\n");
  assert.equal(c, "");
  assert.equal(d, "para two");
});

test("streaming splits and formats complete lines, holds partials", () => {
  const state = createStreamState();
  const parts = [
    formatStreamChunk("# Head", state, { color: false }),
    formatStreamChunk("ing\n- item one\n- item ", state, { color: false }),
    formatStreamChunk("two\n```\ncode\n```", state, { color: false }),
    flushStream(state, { color: false }),
  ];
  const out = parts.join("");
  assert.ok(out.includes("Heading\n"));
  assert.ok(out.includes("• item one\n"));
  assert.ok(out.includes("• item two\n"));
  assert.ok(out.includes("  code"));
});

test("streaming colors bold when enabled", () => {
  const state = createStreamState();
  const out =
    formatStreamChunk("**bold**\n", state, { color: true }) + flushStream(state, { color: true });
  assert.match(out, /\u001b\[1mbold\u001b\[0m/);
});