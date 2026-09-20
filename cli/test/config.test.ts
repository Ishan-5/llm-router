import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  configFilePath,
  loadConfig,
  saveConfig,
  resolveApiKey,
  resolveBaseUrl,
  maskKey,
  byomOverrides,
  setByom,
  removeByom,
  DEFAULT_BASE_URL,
} from "../src/config.js";

const tempDir = join(tmpdir(), `routewise-config-test-${Date.now()}-${Math.floor(Math.random() * 1e6)}`);

before(() => {
  mkdirSync(tempDir, { recursive: true });
  process.env.APPDATA = tempDir;
});

after(() => {
  delete process.env.APPDATA;
  rmSync(tempDir, { recursive: true, force: true });
});

test("configFilePath honors APPDATA", () => {
  const p = configFilePath();
  assert.equal(p, join(tempDir, "routewise", "config.json"));
});

test("save then load roundtrip", () => {
  saveConfig({ api_key: "rw_test", base_url: "https://example.com" });
  const loaded = loadConfig();
  assert.equal(loaded.api_key, "rw_test");
  assert.equal(loaded.base_url, "https://example.com");
});

test("resolveApiKey prefers env over file", () => {
  const saved = { api_key: "rw_file", base_url: undefined } as Record<string, string | undefined>;
  process.env.ROUTEWISE_API_KEY = "rw_env";
  assert.equal(resolveApiKey(saved as never), "rw_env");
  delete process.env.ROUTEWISE_API_KEY;
  assert.equal(resolveApiKey(saved as never), "rw_file");
});

test("resolveBaseUrl falls back to default", () => {
  delete process.env.ROUTEWISE_BASE_URL;
  delete process.env.ROUTEWISE_API_BASE;
  assert.equal(resolveBaseUrl({}), DEFAULT_BASE_URL);
  assert.equal(resolveBaseUrl({ base_url: "https://x.dev" }), "https://x.dev");
});

test("maskKey masks long keys and reports unset", () => {
  assert.match(maskKey("rw_thesecretkey1234"), /^rw_/);
  assert.equal(maskKey(""), "(unset)");
  assert.doesNotMatch(maskKey("rw_thesecretkey1234"), /secretkey/);
});

test("setByom then byomOverrides returns the override", () => {
  setByom("frontier", { provider: "openai", model_id: "gpt-5", api_key: "sk_secret" });
  const overrides = byomOverrides(loadConfig());
  assert.equal(overrides["frontier"]?.provider, "openai");
  assert.equal(overrides["frontier"]?.model_id, "gpt-5");
  assert.equal(overrides["frontier"]?.api_key, "sk_secret");
  assert.equal(overrides["cheap"], undefined);
});

test("removeByom removes one tier and keeps others", () => {
  setByom("cheap", { provider: "groq", model_id: "openai/gpt-oss-20b" });
  setByom("mid", { provider: "groq", model_id: "openai/gpt-oss-20b" });
  removeByom("cheap");
  const overrides = byomOverrides(loadConfig());
  assert.equal(overrides["cheap"], undefined);
  assert.equal(overrides["mid"]?.model_id, "openai/gpt-oss-20b");
});

test("removeByom with no tier clears everything", () => {
  setByom("cheap", { provider: "groq", model_id: "openai/gpt-oss-20b" });
  removeByom();
  assert.deepEqual(byomOverrides(loadConfig()), {});
});