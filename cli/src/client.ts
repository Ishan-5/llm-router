export type RouteTier = "cheap" | "mid" | "frontier";

export type JsonRecord = Record<string, unknown>;

export type RouteWiseErrorKind =
  | "validation"
  | "auth"
  | "rate_limit"
  | "all_failed"
  | "server"
  | "network";

export class RouteWiseError extends Error {
  readonly status: number;
  readonly kind: RouteWiseErrorKind;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown, kind?: RouteWiseErrorKind) {
    super(message);
    this.name = "RouteWiseError";
    this.status = status;
    this.detail = detail;
    this.kind = kind ?? errorKindForStatus(status);
  }
}

export function errorKindForStatus(status: number): RouteWiseErrorKind {
  if (status === 0) {
    return "network";
  }
  if (status === 400) {
    return "validation";
  }
  if (status === 401 || status === 403) {
    return "auth";
  }
  if (status === 429) {
    return "rate_limit";
  }
  if (status === 503) {
    return "all_failed";
  }
  if (status >= 500) {
    return "server";
  }
  return "server";
}

export interface AskOptions {
  query: string;
  overrideTier?: RouteTier;
  threshold?: number;
  bypassCache?: boolean;
  userApiKeys?: Record<string, string>;
  byomConfig?: Record<string, unknown>;
  messages?: Array<{ role: string; content: string }>;
  timeoutMs?: number;
}

export interface ChatOptions {
  messages: Array<{ role: string; content: string }>;
  model?: string;
  maxTokens?: number;
  temperature?: number;
  stream?: boolean;
}

export interface RouteWiseClientOptions {
  apiKey?: string | null;
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

type SseEntry = { kind: "json"; value: JsonRecord } | { kind: "done" } | null;

export function parseSseBlock(block: string): SseEntry[] {
  const entries: SseEntry[] = [];
  for (const line of block.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) {
      continue;
    }
    const payload = trimmed.slice(5).trim();
    if (!payload) {
      continue;
    }
    if (payload === "[DONE]") {
      entries.push({ kind: "done" });
      continue;
    }
    try {
      entries.push({ kind: "json", value: JSON.parse(payload) as JsonRecord });
    } catch {
      entries.push(null);
    }
  }
  return entries;
}

export async function* readJsonSse(
  res: Response,
): AsyncGenerator<JsonRecord, void, unknown> {
  if (!res.body) {
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const blocks: string[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (buffer.length > 0) {
        blocks.push(buffer);
      }
      buffer = "";
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      blocks.push(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
    for (const block of blocks.splice(0, blocks.length)) {
      for (const entry of parseSseBlock(block)) {
        if (entry === null) {
          continue;
        }
        if (entry.kind === "done") {
          return;
        }
        yield entry.value;
      }
    }
  }

  for (const block of blocks.splice(0, blocks.length)) {
    for (const entry of parseSseBlock(block)) {
      if (entry === null) {
        continue;
      }
      if (entry.kind === "done") {
        return;
      }
      yield entry.value;
    }
  }
}

export class RouteWiseClient {
  readonly apiKey: string | null;
  readonly baseUrl: string;
  readonly timeoutMs: number;
  private readonly _fetch: typeof fetch;

  constructor(options: RouteWiseClientOptions = {}) {
    this.apiKey = options.apiKey && options.apiKey.trim() ? options.apiKey.trim() : null;
    this.baseUrl = (options.baseUrl ?? "").trim().replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 120_000;
    this._fetch = options.fetchImpl ?? (globalThis.fetch ?? fetchBinding());
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) {
      h["Authorization"] = `Bearer ${this.apiKey}`;
    }
    return h;
  }

  private buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
    const url = new URL(`${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") {
          url.searchParams.set(k, String(v));
        }
      }
    }
    return url.toString();
  }

  private async request(
    method: string,
    path: string,
    body?: JsonRecord,
    params?: Record<string, string | number | undefined>,
    timeoutMs?: number,
  ): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs ?? this.timeoutMs);
    try {
      const res = await this._fetch(this.buildUrl(path, params), {
        method,
        headers: this.headers(),
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (!res.ok) {
        await this.throwFor(res);
      }
      return res;
    } catch (err) {
      if (err instanceof RouteWiseError) {
        throw err;
      }
      if (err instanceof Error && err.name === "AbortError") {
        throw new RouteWiseError(0, `Request timed out after ${(timeoutMs ?? this.timeoutMs) / 1000}s`, undefined, "network");
      }
      throw new RouteWiseError(0, `Network error: ${(err as Error).message}`, undefined, "network");
    } finally {
      clearTimeout(timer);
    }
  }

  private async throwFor(res: Response): Promise<never> {
    let raw: unknown;
    try {
      raw = await res.json();
    } catch {
      raw = await res.text();
    }
    let message: string;
    if (raw && typeof raw === "object" && "detail" in (raw as object)) {
      const detail = (raw as { detail: unknown }).detail;
      message = typeof detail === "string" ? detail : JSON.stringify(detail);
    } else if (typeof raw === "string") {
      message = raw;
    } else {
      message = JSON.stringify(raw);
    }
    throw new RouteWiseError(res.status, `[${res.status}] ${message}`, raw);
  }

  async ask(options: AskOptions): Promise<JsonRecord> {
    const body: JsonRecord = { query: options.query };
    if (options.overrideTier) {
      body["override_tier"] = options.overrideTier;
    }
    if (options.threshold !== undefined && options.threshold !== null) {
      body["threshold"] = options.threshold;
    }
    if (options.bypassCache) {
      body["bypass_cache"] = true;
    }
    if (options.userApiKeys && Object.keys(options.userApiKeys).length > 0) {
      body["user_api_keys"] = options.userApiKeys;
    }
    if (options.byomConfig && Object.keys(options.byomConfig).length > 0) {
      body["byom_config"] = options.byomConfig;
    }
    if (options.messages && options.messages.length > 0) {
      body["messages"] = options.messages;
    }
    const res = await this.request("POST", "/route", body, undefined, options.timeoutMs);
    return (await res.json()) as JsonRecord;
  }

  async *askStream(
    options: AskOptions,
  ): AsyncGenerator<string | JsonRecord, void, unknown> {
    const body: JsonRecord = { query: options.query };
    if (options.overrideTier) {
      body["override_tier"] = options.overrideTier;
    }
    if (options.threshold !== undefined && options.threshold !== null) {
      body["threshold"] = options.threshold;
    }
    if (options.bypassCache) {
      body["bypass_cache"] = true;
    }
    if (options.userApiKeys && Object.keys(options.userApiKeys).length > 0) {
      body["user_api_keys"] = options.userApiKeys;
    }
    if (options.byomConfig && Object.keys(options.byomConfig).length > 0) {
      body["byom_config"] = options.byomConfig;
    }
    const res = await this.request("POST", "/route/stream", body, undefined, options.timeoutMs ?? 300_000);
    let meta: JsonRecord | null = null;
    for await (const event of readJsonSse(res)) {
      const type = event["type"];
      if (type === "chunk") {
        yield String(event["text"] ?? "");
      } else if (type === "done") {
        meta = event;
      } else if (type === "error") {
        throw new RouteWiseError(res.status, String(event["detail"] ?? "stream error"), event);
      }
    }
    if (meta) {
      yield meta;
    }
  }

  async chat(options: ChatOptions): Promise<JsonRecord> {
    const body: JsonRecord = {
      model: options.model ?? "auto",
      messages: options.messages,
    };
    if (options.maxTokens !== undefined) {
      body["max_tokens"] = options.maxTokens;
    }
    if (options.temperature !== undefined) {
      body["temperature"] = options.temperature;
    }
    const res = await this.request("POST", "/v1/chat/completions", body);
    return (await res.json()) as JsonRecord;
  }

  async *chatStream(options: ChatOptions): AsyncGenerator<JsonRecord, void, unknown> {
    const body: JsonRecord = {
      model: options.model ?? "auto",
      messages: options.messages,
      stream: true,
    };
    if (options.maxTokens !== undefined) {
      body["max_tokens"] = options.maxTokens;
    }
    if (options.temperature !== undefined) {
      body["temperature"] = options.temperature;
    }
    const res = await this.request("POST", "/v1/chat/completions", body, undefined, 300_000);
    for await (const event of readJsonSse(res)) {
      yield event;
    }
  }

  async stats(): Promise<JsonRecord> {
    const res = await this.request("GET", "/stats");
    return (await res.json()) as JsonRecord;
  }

  async logs(limit = 50): Promise<Array<JsonRecord>> {
    const res = await this.request(
      "GET",
      "/logs",
      undefined,
      { limit: Math.min(Math.max(1, limit), 100) },
    );
    return (await res.json()) as Array<JsonRecord>;
  }

  async logDetail(logId: number): Promise<JsonRecord> {
    const res = await this.request("GET", `/logs/${logId}`);
    return (await res.json()) as JsonRecord;
  }

  async analytics(): Promise<JsonRecord> {
    const res = await this.request("GET", "/analytics");
    return (await res.json()) as JsonRecord;
  }

  async compare(): Promise<JsonRecord> {
    const res = await this.request("GET", "/compare");
    return (await res.json()) as JsonRecord;
  }

  async calibrate(): Promise<JsonRecord> {
    const res = await this.request("GET", "/calibrate");
    return (await res.json()) as JsonRecord;
  }

  async pricing(): Promise<Array<JsonRecord>> {
    const res = await this.request("GET", "/pricing");
    return (await res.json()) as Array<JsonRecord>;
  }

  async providers(): Promise<JsonRecord> {
    const res = await this.request("GET", "/providers");
    return (await res.json()) as JsonRecord;
  }

  async feedback(logId: number, feedback: "up" | "down", reason?: string): Promise<JsonRecord> {
    const body: JsonRecord = { request_log_id: logId, feedback };
    if (reason !== undefined && reason.trim() !== "") {
      body["reason"] = reason;
    }
    const res = await this.request("POST", "/route/feedback", body);
    return (await res.json()) as JsonRecord;
  }
}

function fetchBinding(): typeof fetch {
  if (typeof globalThis.fetch !== "function") {
    throw new Error(
      "No global fetch available. Run this on Node.js >= 18 or pass fetchImpl to RouteWiseClient.",
    );
  }
  return globalThis.fetch;
}