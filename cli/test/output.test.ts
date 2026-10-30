import { test } from "node:test";
import assert from "node:assert/strict";
import { metaLine, money, num, printAnalytics, printLogRow, printStats } from "../src/output.js";

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

test("printAnalytics lists spend by team, untagged included", () => {
  const lines = printAnalytics({
    summary: {
      total_requests: 3, total_cost: 0.5, hypothetical_cost: 1.0, savings: 0.5,
      savings_pct: 50, cache_hit_rate: 0, cache_savings: 0, fallback_rate: 0,
    },
    teams: [
      { team_id: "growth", requests: 2, cost_usd: 0.4, saved_usd: 0.3, savings_pct: 42.9 },
      { team_id: null, requests: 1, cost_usd: 0.1, saved_usd: 0, savings_pct: 0 },
    ],
  });
  const text = lines.join("\n");
  assert.match(text, /By team:/);
  assert.match(text, /growth/);
  assert.match(text, /untagged/);
});

test("printAnalytics omits the team section when there is nothing to group", () => {
  const text = printAnalytics({ summary: { total_requests: 0, total_cost: 0 } }).join("\n");
  assert.doesNotMatch(text, /By team:/);
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

test("metaLine names the budget scope that capped the request", () => {
  const line = metaLine({
    routed_to: "cheap",
    cost_usd: 0.00009,
    latency_ms: 940,
    budget_capped: true,
    budget: { state: "exhausted", scope: "team_monthly" },
  });
  assert.match(line, /budget-capped:team_monthly/);
});

test("metaLine flags a budget nearing its cap", () => {
  const line = metaLine({
    routed_to: "mid",
    cost_usd: 0.001,
    budget_capped: false,
    budget: { state: "warning", scope: "key_monthly" },
  });
  assert.match(line, /budget-warning:key_monthly/);
});

test("printAnalytics prints budget posture and downgrade count", () => {
  const text = printAnalytics({
    summary: { total_requests: 10, total_cost: 12.4 },
    budget: {
      state: "exhausted", scope: "team_monthly",
      spent_usd: 12.4, budget_usd: 10, percent_used: 124,
    },
    budget_downgrades_this_month: 2,
  }).join("\n");
  assert.match(text, /Budget\s+exhausted · team_monthly · \$12\.40000 of \$10\.00000 \(124\.0%\)/);
  assert.match(text, /Budget downgrades\s+2 this month/);
});

test("printAnalytics reports an unlimited budget", () => {
  const text = printAnalytics({
    summary: { total_requests: 0 },
    budget: { state: "unlimited" },
  }).join("\n");
  assert.match(text, /Budget\s+unlimited/);
});