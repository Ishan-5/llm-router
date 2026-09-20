#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import {
  clearConfig,
  configFilePath,
  loadConfig,
  maskKey,
  resolveApiKey,
  resolveBaseUrl,
  saveConfig,
  byomOverrides,
  setByom,
  removeByom,
  type TierName,
  type ByomTierConfig,
} from "./config.js";
import { RouteWiseClient, RouteWiseError, type AskOptions, type JsonRecord } from "./client.js";
import { flagBool, flagValue, parseArgs, validTier, type ParsedArgs } from "./parse.js";
import {
  metaLine,
  money,
  num,
  printAnalytics,
  printLogRow,
  printPricing,
  printProviders,
  printStats,
  str,
} from "./output.js";
import { startRepl } from "./repl.js";

const require = createRequire(import.meta.url);
const pkg = require("../../package.json") as { version: string };
const VERSION = pkg.version;

const HELP = `routewise v${VERSION} — cost-aware LLM request router, from your terminal.

Every query is scored for difficulty, then routed to the cheapest model tier
(cheap/mid/frontier) that can handle it — with web search, semantic caching,
and cross-provider failover handled automatically.

Usage:
  routewise ask "<query>"            route one query (answer on stdout, metadata on stderr)
  routewise stream "<query>"         stream tokens as they arrive
  routewise chat                     interactive multi-turn REPL
  echo "…" | routewise ask           pipe a query via stdin
  routewise stats                    usage, cost and savings summary
  routewise logs [--limit N]         recent request log lines
  routewise log <id>                 full detail (incl. response) for one log entry
  routewise analytics                cost analytics + daily breakdown
  routewise compare | calibrate      threshold-vs-cost recommendations (JSON)
  routewise feedback <log_id> <up|down> [reason]   submit thumbs up/down
  routewise pricing                  model price list
  routewise providers                supported providers + models
  routewise config                   show current config
  routewise config set <key>         save an API key
  routewise config set-base <url>    save a base URL
  routewise config unset [key|base]  clear saved config
  routewise config path              print the config file path
  routewise version                  print version
  routewise help                     show this help

Flags (on ask/stream):
  --tier cheap|mid|frontier   force a tier instead of auto-routing
  --threshold <0..2>          routing sensitivity: 0=economy, 1=balanced, 2=quality
  --bypass-cache              skip the semantic cache
  --no-byom                  ignore saved bring-your-own-model settings
  --stream                    stream tokens (equivalent to "routewise stream")
  --json                      print raw JSON response
  --quiet                     suppress the metadata line on stderr
  --base-url <url>            override the API base URL for this call
  --key <key>                 use an API key for this call only

Bring your own model (saved once locally, auto-applied to every ask/stream):
  routewise byom set <cheap|mid|frontier> --provider <p> --model <m> [--key <k>]
  routewise byom list
  routewise byom remove <tier> | routewise byom remove --all

Config:
  Settings are read from ROUTEWISE_API_KEY / ROUTEWISE_BASE_URL env vars, then
  from ${configFilePath()}. Default base URL: https://llm-router-d2b2.onrender.com
`;

function printHelp(): void {
  process.stdout.write(HELP + "\n");
}

function requireKey(client: RouteWiseClient): RouteWiseClient {
  if (!client.apiKey) {
    throw new Error(
      "No API key set. Create one via the dashboard, then run:\n  routewise config set <key>\n(or export ROUTEWISE_API_KEY=<key>)",
    );
  }
  return client;
}

function queryFrom(positionals: string[]): string {
  const joined = positionals.join(" ").trim();
  if (joined) {
    return joined;
  }
  if (process.stdin.isTTY) {
    return "";
  }
  try {
    return readFileSync(0, "utf8").trim();
  } catch {
    return "";
  }
}

function limitFrom(flags: ParsedArgs["flags"], fallback: number): number {
  const raw = flagValue(flags, "limit");
  if (!raw) {
    return fallback;
  }
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? Math.min(n, 100) : fallback;
}

function printJson(value: unknown): void {
  process.stdout.write(JSON.stringify(value, null, 2) + "\n");
}

async function askOptionsFrom(
  flags: ParsedArgs["flags"],
  positionals: string[],
  byom: Partial<Record<TierName, ByomTierConfig>> = {},
): Promise<AskOptions> {
  const query = queryFrom(positionals);
  if (!query) {
    throw new Error('Missing query. Usage: routewise ask "<query>" (or pipe via stdin).');
  }
  const tierRaw = flagValue(flags, "tier");
  const tier = validTier(tierRaw);
  if (tierRaw && !tier) {
    throw new Error("--tier must be cheap, mid, or frontier");
  }
  let threshold: number | undefined;
  const thresholdRaw = flagValue(flags, "threshold");
  if (thresholdRaw) {
    const n = Number(thresholdRaw);
    if (!Number.isFinite(n) || n < 0 || n > 2) {
      throw new Error("--threshold must be a number between 0 and 2");
    }
    threshold = n;
  }
  const options: AskOptions = {
    query,
    overrideTier: tier ?? undefined,
    threshold,
    bypassCache: flagBool(flags, "bypass-cache"),
  };
  if (!flagBool(flags, "no-byom")) {
    const byomConfig: Record<string, unknown> = {};
    const userApiKeys: Record<string, string> = {};
    for (const [t, cfg] of Object.entries(byom)) {
      byomConfig[t] = { provider: cfg.provider, model_id: cfg.model_id };
      if (cfg.api_key) {
        userApiKeys[t] = cfg.api_key;
      }
    }
    if (Object.keys(byomConfig).length > 0) {
      options.byomConfig = byomConfig;
    }
    if (Object.keys(userApiKeys).length > 0) {
      options.userApiKeys = userApiKeys;
    }
  }
  return options;
}

async function cmdAsk(
  client: RouteWiseClient,
  flags: ParsedArgs["flags"],
  positionals: string[],
  forceStream = false,
  byom: Partial<Record<TierName, ByomTierConfig>> = {},
): Promise<void> {
  requireKey(client);
  const options = await askOptionsFrom(flags, positionals, byom);
  const json = flagBool(flags, "json");
  const quiet = flagBool(flags, "quiet");
  const stream = forceStream || flagBool(flags, "stream");

  if (!stream) {
    const res = await client.ask(options);
    if (json) {
      printJson(res);
      return;
    }
    process.stdout.write(str(res["response"]) + "\n");
    if (!quiet) {
      process.stderr.write(metaLine(res) + "\n");
    }
    return;
  }

  let meta: JsonRecord | null = null;
  let wrote = false;
  for await (const item of client.askStream(options)) {
    if (typeof item === "string") {
      process.stdout.write(item);
      wrote = true;
    } else {
      meta = item;
    }
  }
  if (wrote) {
    process.stdout.write("\n");
  }
  if (!quiet && meta) {
    process.stderr.write(metaLine(meta) + "\n");
  }
}

async function cmdChat(
  client: RouteWiseClient,
  flags: ParsedArgs["flags"],
  positionals: string[],
): Promise<number> {
  requireKey(client);
  const tierRaw = flagValue(flags, "tier");
  const tier = validTier(tierRaw);
  if (tierRaw && !tier) {
    throw new Error("--tier must be cheap, mid, or frontier");
  }
  const initialQuery = queryFrom(positionals);
  return startRepl({
    client,
    model: tier ?? "auto",
    json: flagBool(flags, "json"),
    initialQuery: initialQuery || undefined,
  });
}

function validTierName(value: string | null): TierName | null {
  return value === "cheap" || value === "mid" || value === "frontier" ? value : null;
}

function cmdByom(
  positionals: string[],
  flags: ParsedArgs["flags"],
): void {
  const file = loadConfig();
  const sub = positionals[0] ?? "list";
  const json = flagBool(flags, "json");
  const byom = byomOverrides(file);

  const current: JsonRecord = {};
  for (const [t, cfg] of Object.entries(byom)) {
    current[t] = {
      provider: String(cfg.provider),
      model_id: String(cfg.model_id),
      api_key: cfg.api_key ? maskKey(cfg.api_key) : undefined,
    };
  }

  if (sub === "list" || sub === "show") {
    if (json) {
      printJson(current);
      return;
    }
    const keys = Object.keys(current);
    if (keys.length === 0) {
      console.log("No BYOM overrides saved. Add one with:");
      console.log('  routewise byom set <cheap|mid|frontier> --provider <p> --model <m> [--key <k>]');
      return;
    }
    for (const t of keys) {
      const cfg = current[t] as JsonRecord;
      console.log(`[${t}] ${str(cfg["provider"])} / ${str(cfg["model_id"])}${cfg["api_key"] ? `  key=${str(cfg["api_key"])}` : "  (uses server keys)"}`);
    }
    console.log("\nApplied automatically to every ask/stream. Remove with:");
    console.log("  routewise byom remove <tier>   (or: routewise byom remove --all)");
    return;
  }

  if (sub === "set") {
    const tier = validTierName(positionals[1] ?? null);
    if (!tier) {
      throw new Error("Usage: routewise byom set <cheap|mid|frontier> --provider <p> --model <m> [--key <k>]");
    }
    const provider = flagValue(flags, "provider");
    const model = flagValue(flags, "model");
    if (!provider || !model) {
      throw new Error("byom set requires --provider and --model");
    }
    const key = flagValue(flags, "key") ?? undefined;
    setByom(tier, { provider, model_id: model, api_key: key });
    console.log(`Saved [${tier}] → ${provider} / ${model}${key ? " (with your key)" : " (server keys)"}.`);
    return;
  }

  if (sub === "remove" || sub === "rm") {
    if (flagBool(flags, "all") || positionals.length < 2) {
      removeByom();
      console.log("Removed all BYOM overrides.");
    } else {
      const tier = validTierName(positionals[1] ?? null);
      if (!tier) {
        throw new Error("Usage: routewise byom remove <cheap|mid|frontier> | routewise byom remove --all");
      }
      removeByom(tier);
      console.log(`Removed [${tier}] BYOM override.`);
    }
    return;
  }

  throw new Error(`Unknown byom subcommand: ${sub}. Try "routewise byom list".`);
}

function cmdConfig(
  positionals: string[],
  flags: ParsedArgs["flags"],
): void {
  const sub = positionals[0];
  const file = loadConfig();
  const json = flagBool(flags, "json");

  if (sub === "set") {
    let key = positionals[1];
    if (!key && !process.stdin.isTTY) {
      key = queryFrom([]);
    }
    if (!key) {
      throw new Error("Usage: routewise config set <key>");
    }
    saveConfig({ api_key: key.trim() });
    console.log(`Saved API key to ${configFilePath()}`);
    return;
  }

  if (sub === "set-base") {
    const url = positionals[1];
    if (!url) {
      throw new Error("Usage: routewise config set-base <url>");
    }
    saveConfig({ base_url: url.trim() });
    console.log(`Saved base URL to ${configFilePath()}`);
    return;
  }

  if (sub === "unset") {
    const target = positionals[1] ?? "all";
    if (target === "base" || target === "base-url") {
      saveConfig({ base_url: "" });
    } else if (target === "key" || target === "api") {
      saveConfig({ api_key: "" });
    } else {
      saveConfig({ api_key: "" });
      saveConfig({ base_url: "" });
    }
    console.log("Config updated.");
    return;
  }

  if (sub === "clear") {
    clearConfig();
    console.log(`Removed ${configFilePath()}`);
    return;
  }

  if (sub === "path") {
    console.log(configFilePath());
    return;
  }

  const byom = byomOverrides(file);
  const byomSummary = (Object.keys(byom).length > 0)
    ? Object.entries(byom)
        .map(([t, c]) => `${t} → ${c.provider}/${c.model_id}`)
        .join(", ")
    : "none";

  const envKey = process.env.ROUTEWISE_API_KEY?.trim() || "";
  const savedKey = file.api_key?.trim() || "";
  const key = envKey || savedKey || "";
  const envBase =
    process.env.ROUTEWISE_BASE_URL?.trim() ||
    process.env.ROUTEWISE_API_BASE?.trim() ||
    "";
  const base = envBase || file.base_url?.trim() || resolveBaseUrl(file);
  const cfg: JsonRecord = {
    base_url: base,
    api_key: key ? maskKey(key) : "(unset)",
    api_key_source: envKey ? "environment" : savedKey ? "config file" : "not set",
    config_file: configFilePath(),
  };
  if (json) {
    printJson(cfg);
    return;
  }
  console.log(`Base URL:    ${base}`);
  console.log(`API key:     ${key ? maskKey(key) : "(unset)"}`);
  console.log(`Key source:  ${envKey ? "environment" : savedKey ? "config file" : "not set"}`);
  console.log(`BYOM:        ${byomSummary}`);
  console.log(`Config file: ${configFilePath()}`);
  if (!key) {
    console.log("Hint: save a key with: routewise config set <key>");
  }
}

async function cmdStats(client: RouteWiseClient, flags: ParsedArgs["flags"]): Promise<void> {
  requireKey(client);
  const res = await client.stats();
  if (flagBool(flags, "json")) {
    printJson(res);
    return;
  }
  console.log(printStats(res).join("\n"));
}

async function cmdLogs(client: RouteWiseClient, flags: ParsedArgs["flags"]): Promise<void> {
  requireKey(client);
  const rows = await client.logs(limitFrom(flags, 50));
  if (flagBool(flags, "json")) {
    printJson(rows);
    return;
  }
  if (rows.length === 0) {
    console.log("No requests logged yet.");
    return;
  }
  for (const row of rows) {
    console.log(printLogRow(row));
  }
}

async function cmdLog(client: RouteWiseClient, flags: ParsedArgs["flags"], positionals: string[]): Promise<void> {
  const id = Number(positionals[0]);
  if (!Number.isInteger(id) || id <= 0) {
    throw new Error("Usage: routewise log <id>");
  }
  const row = await client.logDetail(id);
  if (flagBool(flags, "json")) {
    printJson(row);
    return;
  }
  const score = num(row["difficulty_score"]);
  console.log(`id:        ${str(row["id"])}`);
  console.log(`query:     ${str(row["query"] ?? "")}`);
  console.log(`tier:      ${str(row["tier"] ?? "-")} (intended ${str(row["intended_tier"] ?? "-")})`);
  console.log(`model:     ${str(row["model_id"] ?? "-")}`);
  console.log(`score:     ${score !== null ? score.toFixed(2) : "-"}`);
  console.log(`cost:      ${money(row["cost_usd"])}`);
  console.log(`latency:   ${str(row["latency_ms"] ?? "-")}ms`);
  console.log(`cache:     ${row["cache_hit"] ? `yes (sim ${num(row["cache_similarity"]) ?? "-"})` : "no"}`);
  console.log(`tokens:    ${num(row["input_tokens"]) ?? 0} in / ${num(row["output_tokens"]) ?? 0} out`);
  console.log(`created:   ${str(row["created_at"] ?? "-")}`);
  console.log("");
  console.log(str(row["response"] ?? "(no response stored)"));
}

async function cmdAnalytics(client: RouteWiseClient, flags: ParsedArgs["flags"]): Promise<void> {
  requireKey(client);
  const res = await client.analytics();
  if (flagBool(flags, "json")) {
    printJson(res);
    return;
  }
  console.log(printAnalytics(res).join("\n"));
}

async function cmdPricing(client: RouteWiseClient, flags: ParsedArgs["flags"]): Promise<void> {
  const rows = await client.pricing();
  if (flagBool(flags, "json")) {
    printJson(rows);
    return;
  }
  console.log(printPricing(rows).join("\n"));
}

async function cmdProviders(client: RouteWiseClient, flags: ParsedArgs["flags"]): Promise<void> {
  const res = await client.providers();
  if (flagBool(flags, "json")) {
    printJson(res);
    return;
  }
  console.log(printProviders(res).join("\n"));
}

async function cmdFeedback(client: RouteWiseClient, flags: ParsedArgs["flags"], positionals: string[]): Promise<void> {
  requireKey(client);
  const id = Number(positionals[0]);
  const fb = positionals[1];
  if (!Number.isInteger(id) || id <= 0 || (fb !== "up" && fb !== "down")) {
    throw new Error("Usage: routewise feedback <log_id> <up|down> [reason]");
  }
  const reason = positionals.slice(2).join(" ") || undefined;
  const res = await client.feedback(id, fb, reason);
  if (flagBool(flags, "json")) {
    printJson(res);
    return;
  }
  console.log(`Saved ${fb} feedback for log ${id}.`);
}

export async function run(argv: string[]): Promise<number> {
  let parsed: ParsedArgs;
  try {
    parsed = parseArgs(argv);
  } catch (err) {
    process.stderr.write(`routewise: ${(err as Error).message}\n`);
    return 1;
  }

  const { command, positionals, flags } = parsed;

  if (flagBool(flags, "version") || command === "version") {
    console.log(VERSION);
    return 0;
  }
  if (flagBool(flags, "help") || command === "help") {
    printHelp();
    return 0;
  }

  const file = loadConfig();
  const apiKey = flagValue(flags, "key") ?? resolveApiKey(file);
  const baseUrl = flagValue(flags, "base-url") ?? resolveBaseUrl(file);
  const byom = byomOverrides(file);
  const client = new RouteWiseClient({ apiKey, baseUrl });

  try {
    switch (command) {
      case "ask":
        await cmdAsk(client, flags, positionals, false, byom);
        break;
      case "stream":
        await cmdAsk(client, flags, positionals, true, byom);
        break;
      case "chat":
        return await cmdChat(client, flags, positionals);
      case "config":
        cmdConfig(positionals, flags);
        break;
      case "byom":
        cmdByom(positionals, flags);
        break;
      case "stats":
        await cmdStats(client, flags);
        break;
      case "logs":
        await cmdLogs(client, flags);
        break;
      case "log":
        await cmdLog(client, flags, positionals);
        break;
      case "analytics":
        await cmdAnalytics(client, flags);
        break;
      case "pricing":
        await cmdPricing(client, flags);
        break;
      case "providers":
        await cmdProviders(client, flags);
        break;
      case "compare":
      case "calibrate":
        requireKey(client);
        printJson(await (command === "compare" ? client.compare() : client.calibrate()));
        break;
      case "feedback":
        await cmdFeedback(client, flags, positionals);
        break;
      default:
        throw new Error(`Unknown command: ${command}. Run "routewise help".`);
    }
  } catch (err) {
    process.stderr.write(`routewise: ${(err as Error).message}\n`);
    if (err instanceof RouteWiseError) {
      process.stderr.write(`(HTTP ${err.status})\n`);
    }
    return 1;
  }

  return 0;
}

const exitCode = await run(process.argv.slice(2));
process.exitCode = exitCode;