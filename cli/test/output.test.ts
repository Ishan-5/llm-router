import { test } from "node:test";
import assert from "node:assert/strict";
import { metaLine, money, num, printLogRow, printStats } from "../src/output.js";

test("money formatting", () => {
  assert.equal(money(0.00012345), "$0.00012");
  assert.equal(money(null), "-");
  assert.equal(money(undefined), "-");
});

test("num returns numbers only", () => {
  assert.equal(num(4.5), 4.5);
  assert.equal(num("4.5"), null);
  assert.equal(num(null), null);
});

test("metaLine formats live routing", () => {
  const res = {
    response: "x",
    routed_to: "cheap",
    difficulty_score: 4.52,
    cost_usd: 0.00008,
    latency_ms: 812,
    cache_hit: false,
  };
  const line = metaLine(res);
  assert.match(line, /^\[cheap score=4\.52 \$0\.00008 · 812ms\]$/);
});

test("metaLine flags cache hit", () => {
  const line = metaLine({ routed_to: "mid", cache_hit: true, cost_usd: 0 });
  assert.match(line, /cache/);
});

test("metaLine flags fallback", () => {
  const line = metaLine({
    routed_to: "cheap",
    intended_tier: "frontier",
    fallback_used: true,
    cost_usd: 0.0001,
    latency_ms: 100,
  });
  assert.match(line, /fallback:frontier->cheap/);
});

test("printLogRow pads columns", () => {
  const row = {
    id: 42,
    tier: "cheap",
    model_id: "deepseek/deepseek-v4-flash",
    cost_usd: 0.00005,
    latency_ms: 200,
    cache_hit: false,
    query: "what is the capital of france",
  };
  const line = printLogRow(row);
  assert.match(line, /42\s+cheap\s+deepseek/);
  assert.match(line, /what is the capital/);
});

test("printStats renders summary fields", () => {
  const stats = {
    total_requests: 10,
    total_actual_cost: 0.001,
    total_hypothetical_cost: 0.002,
    routing_savings_usd: 0.001,
    cache_savings_usd: 0.0001,
    total_savings_usd: 0.0011,
    cache_hit_rate: 0.34,
    fallback_count: 1,
    feedback_counts: { up: 2, down: 1 },
    tier_counts: { cheap: 6, mid: 3, frontier: 1 },
    avg_latency_by_tier: { cheap: 100, mid: 200 },
  };
  const lines = printStats(stats);
  assert.ok(lines.some((l) => l.includes("Requests") && l.includes("10")));
  assert.ok(lines.some((l) => l.includes("Cache hit rate") && l.includes("34.0%")));
  assert.ok(lines.some((l) => l.includes("cheap 6") && l.includes("mid 3")));
});