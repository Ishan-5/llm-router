import { test } from "node:test";
import assert from "node:assert/strict";
import { RouteWiseClient, RouteWiseError, parseSseBlock, readJsonSse } from "../src/client.js";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sseResponse(body: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

test("ask sends query and auth header", async () => {
  let capturedUrl = "";
  let capturedHeaders: Headers | Record<string, string> = {};
  let capturedBody = "";
  const client = new RouteWiseClient({
    apiKey: "rw_test",
    baseUrl: "https://example.com",
    fetchImpl: (async (url: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedHeaders = init?.headers ? Object.fromEntries(new Headers(init.headers).entries()) : {};
      capturedBody = String(init?.body ?? "");
      return jsonResponse({ response: "hi", routed_to: "cheap" });
    }) as typeof fetch,
  });
  const res = await client.ask({ query: "hello" });
  assert.equal(res["routed_to"], "cheap");
  assert.equal(capturedUrl, "https://example.com/route");
  assert.match(capturedBody, /hello/);
  assert.match(String(capturedHeaders["authorization"]), /Bearer rw_test/);
});

test("ask passes override tier, threshold and bypass cache", async () => {
  let capturedBody = "";
  const client = new RouteWiseClient({
    apiKey: "rw_test",
    baseUrl: "https://example.com",
    fetchImpl: (async (_url: RequestInfo | URL, init?: RequestInit) => {
      capturedBody = String(init?.body ?? "");
      return jsonResponse({ response: "x", routed_to: "frontier" });
    }) as typeof fetch,
  });
  await client.ask({ query: "q", overrideTier: "frontier", threshold: 2, bypassCache: true });
  const body = JSON.parse(capturedBody) as Record<string, unknown>;
  assert.equal(body["override_tier"], "frontier");
  assert.equal(body["threshold"], 2);
  assert.equal(body["bypass_cache"], true);
});

test("ask forwards byom config and user api keys", async () => {
  let capturedBody = "";
  const client = new RouteWiseClient({
    apiKey: "rw_test",
    baseUrl: "https://example.com",
    fetchImpl: (async (_url: RequestInfo | URL, init?: RequestInit) => {
      capturedBody = String(init?.body ?? "");
      return jsonResponse({ response: "x", routed_to: "mid" });
    }) as typeof fetch,
  });
  await client.ask({
    query: "q",
    byomConfig: { mid: { provider: "openai", model_id: "gpt-5" } },
    userApiKeys: { mid: "sk_userkey" },
  });
  const body = JSON.parse(capturedBody) as Record<string, unknown>;
  assert.deepEqual(body["byom_config"], { mid: { provider: "openai", model_id: "gpt-5" } });
  assert.deepEqual(body["user_api_keys"], { mid: "sk_userkey" });
});

test("maps error statuses to kinds", async () => {
  const respond = (status: number) =>
    new RouteWiseClient({
      apiKey: "rw_test",
      baseUrl: "https://example.com",
      fetchImpl: (async (_url: RequestInfo | URL) =>
        jsonResponse({ detail: "nope" }, status)) as typeof fetch,
    });

  await assert.rejects(() => respond(400).ask({ query: "q" }), (e: RouteWiseError) => e.kind === "validation");
  await assert.rejects(() => respond(401).ask({ query: "q" }), (e: RouteWiseError) => e.kind === "auth");
  await assert.rejects(() => respond(429).ask({ query: "q" }), (e: RouteWiseError) => e.kind === "rate_limit");
  await assert.rejects(() => respond(503).ask({ query: "q" }), (e: RouteWiseError) => e.kind === "all_failed");
});

test("no key means no auth header", async () => {
  let auth = "";
  const client = new RouteWiseClient({
    baseUrl: "https://example.com",
    fetchImpl: (async (_url: RequestInfo | URL, init?: RequestInit) => {
      auth = String(init?.headers ? (init.headers as Record<string, string>)["Authorization"] ?? "" : "");
      return jsonResponse({ ok: true });
    }) as typeof fetch,
  });
  await client.ask({ query: "q" });
  assert.equal(auth, "");
});

test("parseSseBlock handles json and [DONE]", () => {
  const entries = parseSseBlock('data: {"type":"chunk","text":"a"}\ndata: [DONE]');
  assert.equal(entries.length, 2);
  assert.equal((entries[0] as { kind: "json"; value: Record<string, unknown> }).value["text"], "a");
  assert.equal((entries[1] as { kind: "done" }).kind, "done");
});

test("readJsonSse streams multi-block SSE", async () => {
  const body =
    'data: {"type":"chunk","text":"A"}\n\n' +
    'data: {"type":"chunk","text":"B"}\n' +
    'data: {"type":"meta","x":1}\n\n' +
    'data: {"type":"done","routed_to":"mid","cost_usd":0}\n\n';
  const res = sseResponse(body);
  const got: Array<Record<string, unknown>> = [];
  for await (const ev of readJsonSse(res)) {
    got.push(ev);
  }
  assert.equal(got.length, 4);
  assert.equal(got[0]["text"], "A");
  assert.equal(got[1]["text"], "B");
  assert.equal(got[2]["type"], "meta");
  assert.equal(got[3]["routed_to"], "mid");
});

test("askStream yields text then meta", async () => {
  const body =
    'data: {"type":"chunk","text":"Hello,"}\n\n' +
    'data: {"type":"chunk","text":" world"}\n\n' +
    'data: {"type":"done","routed_to":"cheap","cost_usd":0.0001,"latency_ms":50,"difficulty_score":3.25}\n\n';
  const client = new RouteWiseClient({
    apiKey: "rw_test",
    baseUrl: "https://example.com",
    fetchImpl: (async (_url: RequestInfo | URL) => sseResponse(body)) as typeof fetch,
  });
  const parts = [];
  for await (const item of client.askStream({ query: "q" })) {
    parts.push(item);
  }
  assert.equal(parts[0], "Hello,");
  assert.equal(parts[1], " world");
  const meta = parts[2] as Record<string, unknown>;
  assert.equal(meta["routed_to"], "cheap");
});

test("chat returns non-stream JSON", async () => {
  const client = new RouteWiseClient({
    apiKey: "rw_test",
    baseUrl: "https://example.com",
    fetchImpl: (async (_url: RequestInfo | URL) =>
      jsonResponse({ choices: [{ message: { content: "hi" } }] })) as typeof fetch,
  });
  const res = await client.chat({ messages: [{ role: "user", content: "q" }] });
  const choices = res["choices"] as Array<Record<string, unknown>>;
  assert.equal((choices[0]["message"] as Record<string, unknown>)["content"], "hi");
});

test("evaluate posts queries without auth", async () => {
  let capturedUrl = "";
  let capturedHeaders: Headers | Record<string, string> = {};
  let capturedBody = "";
  const client = new RouteWiseClient({
    baseUrl: "https://example.com",
    fetchImpl: (async (url: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedHeaders = init?.headers ? Object.fromEntries(new Headers(init.headers).entries()) : {};
      capturedBody = String(init?.body ?? "");
      return jsonResponse({
        results: [{ query: "q", difficulty_score: 4.2, tier_economy: "mid" }],
        thresholds: [],
      });
    }) as typeof fetch,
  });
  const res = await client.evaluate(["q"]);
  assert.equal(capturedUrl, "https://example.com/evaluate");
  assert.deepEqual(JSON.parse(capturedBody), { queries: ["q"] });
  assert.equal(capturedHeaders["authorization"], undefined);
  assert.equal((res["results"] as Array<{ difficulty_score: number }>)[0]["difficulty_score"], 4.2);
});

test("evaluate rejects empty query list", async () => {
  const client = new RouteWiseClient({
    baseUrl: "https://example.com",
    fetchImpl: (async () => jsonResponse({})) as typeof fetch,
  });
  await assert.rejects(() => client.evaluate(["  "]), /needs at least one query/);
});

test("health resolves true on 200 and false on failure", async () => {
  const okClient = new RouteWiseClient({
    baseUrl: "https://example.com",
    fetchImpl: (async () => jsonResponse({ ok: true })) as typeof fetch,
  });
  assert.equal(await okClient.health(), true);

  const downClient = new RouteWiseClient({
    baseUrl: "https://example.com",
    fetchImpl: (async () => {
      throw new Error("ECONNREFUSED");
    }) as typeof fetch,
  });
  assert.equal(await downClient.health(), false);
});