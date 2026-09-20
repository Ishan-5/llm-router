import type { JsonRecord } from "./client.js";

export function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function str(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

export function money(value: unknown): string {
  const n = num(value);
  if (n === null) {
    return "-";
  }
  return `$${n.toFixed(5)}`;
}

export function metaTags(res: JsonRecord): string[] {
  const tags: string[] = [];
  if (res["cache_hit"]) {
    tags.push("cache");
  }
  if (res["routed_to"] === "web") {
    tags.push("web");
  }
  const intended = str(res["intended_tier"]);
  const routed = str(res["routed_to"]);
  if (res["fallback_used"]) {
    tags.push(`fallback:${intended || "-"}->${routed || "-"}`);
  }
  if (res["cross_provider_fallback"]) {
    tags.push("cross-provider");
  }
  if (res["budget_capped"]) {
    tags.push("budget-capped");
  }
  if (res["override_used"]) {
    tags.push("override");
  }
  return tags;
}

export function metaLine(res: JsonRecord): string {
  const score = num(res["difficulty_score"]);
  const scorePart = score !== null ? ` score=${score.toFixed(2)}` : "";
  const latency = num(res["latency_ms"]);
  const latencyPart = latency !== null ? ` · ${latency}ms` : "";
  const tags = metaTags(res);
  const tagPart = tags.length > 0 ? ` ${tags.join(", ")}` : "";
  return `[${str(res["routed_to"]) || "-"}${scorePart} ${money(res["cost_usd"])}${latencyPart}${tagPart}]`;
}

export function printStats(res: JsonRecord): string[] {
  const tierCounts = (res["tier_counts"] as Record<string, number> | undefined) ?? {};
  const tierSplit = Object.entries(tierCounts)
    .map(([k, v]) => `${k} ${v}`)
    .join(" · ");
  const cacheRate = num(res["cache_hit_rate"]);
  const lines: string[] = [];
  lines.push(`Requests            ${num(res["total_requests"]) ?? 0}`);
  lines.push(`Total cost          ${money(res["total_actual_cost"])}`);
  lines.push(`Hypothetical cost   ${money(res["total_hypothetical_cost"])}`);
  lines.push(`Routing savings     ${money(res["routing_savings_usd"])}`);
  lines.push(`Cache savings       ${money(res["cache_savings_usd"])}`);
  lines.push(`Total savings       ${money(res["total_savings_usd"])}`);
  lines.push(`Cache hit rate      ${cacheRate !== null ? `${(cacheRate * 100).toFixed(1)}%` : "-"}`);
  lines.push(`Fallbacks           ${num(res["fallback_count"]) ?? 0}`);
  const feedback = (res["feedback_counts"] as Record<string, number> | undefined) ?? {};
  lines.push(`Feedback            ${num(feedback["up"]) ?? 0} up · ${num(feedback["down"]) ?? 0} down`);
  if (tierSplit) {
    lines.push(`Tier split          ${tierSplit}`);
  }
  const avgLatency = (res["avg_latency_by_tier"] as Record<string, number> | undefined) ?? {};
  const latParts = Object.entries(avgLatency)
    .map(([k, v]) => `${k} ${num(v)?.toFixed(0) ?? "?"}ms`)
    .join(" · ");
  if (latParts) {
    lines.push(`Latency by tier     ${latParts}`);
  }
  return lines;
}

export function printLogRow(row: JsonRecord): string {
  const id = String(row["id"] ?? "?").padEnd(5);
  const tier = str(row["tier"] ?? "").padEnd(8).slice(0, 8);
  const model = str(row["model_id"] ?? "-").padEnd(26).slice(0, 26);
  const cost = money(row["cost_usd"]).padEnd(11);
  const latency = str(row["latency_ms"] ?? "-").padEnd(8);
  const cache = row["cache_hit"] ? "yes" : "no";
  const query = str(row["query"] ?? "").slice(0, 60);
  return `${id} ${tier} ${model} ${cost} ${latency} ${cache.padEnd(4)} ${query}`;
}

export function printAnalytics(res: JsonRecord): string[] {
  const summary = (res["summary"] as JsonRecord | undefined) ?? {};
  const lines: string[] = [];
  lines.push(`Requests            ${num(summary["total_requests"]) ?? 0}`);
  lines.push(`Total cost          ${money(summary["total_cost"])}`);
  lines.push(`Hypothetical cost   ${money(summary["hypothetical_cost"])}`);
  lines.push(`Savings             ${money(summary["savings"])}`);
  lines.push(`Savings vs frontier ${num(summary["savings_pct"]) !== null ? `${num(summary["savings_pct"])?.toFixed(1)}%` : "-"}`);
  lines.push(`Cache hit rate      ${num(summary["cache_hit_rate"]) !== null ? `${num(summary["cache_hit_rate"])?.toFixed(1)}%` : "-"}`);
  lines.push(`Cache savings       ${money(summary["cache_savings"])}`);
  lines.push(`Fallback rate       ${num(summary["fallback_rate"]) !== null ? `${num(summary["fallback_rate"])?.toFixed(1)}%` : "-"}`);
  const daily = res["daily"];
  if (Array.isArray(daily) && daily.length > 0) {
    lines.push("");
    lines.push("Daily:");
    for (const d of daily as Array<JsonRecord>) {
      lines.push(`  ${str(d["date"])}  ${money(d["cost"])}  ${num(d["requests"]) ?? 0} req  ${num(d["avg_latency"]) !== null ? `${num(d["avg_latency"])?.toFixed(0)}ms` : "-"}`);
    }
  }
  return lines;
}

export function printProviders(res: JsonRecord): string[] {
  const lines: string[] = [];
  for (const [provider, info] of Object.entries(res)) {
    const label = str((info as JsonRecord)["label"] ?? provider);
    const models = (info as JsonRecord)["models"];
    const modelList = Array.isArray(models) ? (models as unknown[]).join(", ") : "";
    lines.push(`${provider} (${label})`);
    if (modelList) {
      lines.push(`  ${modelList}`);
    }
  }
  return lines;
}

export function printPricing(rows: Array<JsonRecord>): string[] {
  const head = `${"PROVIDER".padEnd(12)} ${"MODEL".padEnd(30)} ${"IN".padEnd(9)} ${"OUT".padEnd(9)} ${"NOTES"}`;
  const body = rows.map((r) => {
    const provider = str(r["provider"]).padEnd(12).slice(0, 12);
    const model = str(r["model_id"]).padEnd(30).slice(0, 30);
    const inn = num(r["price_per_m_input"]);
    const out = num(r["price_per_m_output"]);
    return `${provider} ${model} ${inn !== null ? `$${inn.toFixed(4)}` : "-".padEnd(9)} ${out !== null ? `$${out.toFixed(4)}` : "-".padEnd(9)} ${str(r["notes"] ?? "")}`;
  });
  return [head, ...body];
}