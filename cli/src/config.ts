import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";

export const DEFAULT_BASE_URL = "https://llm-router-d2b2.onrender.com";

export type TierName = "cheap" | "mid" | "frontier";

export interface ByomTierConfig {
  provider: string;
  model_id: string;
  api_key?: string;
}

export interface RouteWiseConfig {
  api_key?: string;
  base_url?: string;
  byom?: Partial<Record<TierName, ByomTierConfig>>;
}

export function configFilePath(): string {
  const appData = process.env.APPDATA;
  const base = appData ? join(appData, "routewise") : join(homedir(), ".config", "routewise");
  return join(base, "config.json");
}

export function loadConfig(): RouteWiseConfig {
  try {
    const raw = readFileSync(configFilePath(), "utf8");
    const parsed = JSON.parse(raw) as RouteWiseConfig;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function saveConfig(partial: RouteWiseConfig): RouteWiseConfig {
  const file = configFilePath();
  const next = { ...loadConfig(), ...partial };
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(next, null, 2) + "\n", { mode: 0o600 });
  return next;
}

export function clearConfig(): void {
  const file = configFilePath();
  if (existsSync(file)) {
    rmSync(file);
  }
}

export function resolveApiKey(file: RouteWiseConfig): string | null {
  const env = process.env.ROUTEWISE_API_KEY;
  if (env && env.trim()) {
    return env.trim();
  }
  if (file.api_key && file.api_key.trim()) {
    return file.api_key.trim();
  }
  return null;
}

export function resolveBaseUrl(file: RouteWiseConfig): string {
  const env =
    process.env.ROUTEWISE_BASE_URL?.trim() ||
    process.env.ROUTEWISE_API_BASE?.trim();
  if (env) {
    return env;
  }
  if (file.base_url && file.base_url.trim()) {
    return file.base_url.trim();
  }
  return DEFAULT_BASE_URL;
}

export function maskKey(key: string): string {
  if (!key) {
    return "(unset)";
  }
  if (key.length <= 8) {
    return "••••";
  }
  return `${key.slice(0, 5)}••••${key.slice(-4)}`;
}

export function byomOverrides(file: RouteWiseConfig): Partial<Record<TierName, ByomTierConfig>> {
  return file.byom && typeof file.byom === "object" ? file.byom : {};
}

export function setByom(tier: TierName, cfg: ByomTierConfig): RouteWiseConfig {
  const file = loadConfig();
  const next: Partial<Record<TierName, ByomTierConfig>> = {
    ...byomOverrides(file),
    [tier]: {
      provider: cfg.provider.trim(),
      model_id: cfg.model_id.trim(),
      api_key: cfg.api_key && cfg.api_key.trim() ? cfg.api_key.trim() : undefined,
    },
  };
  saveConfig({ byom: next } as RouteWiseConfig);
  return loadConfig();
}

export function removeByom(tier?: TierName): RouteWiseConfig {
  const file = loadConfig();
  const current: Partial<Record<TierName, ByomTierConfig>> = {
    ...byomOverrides(file),
  };
  if (tier) {
    delete current[tier];
  } else {
    delete current["cheap"];
    delete current["mid"];
    delete current["frontier"];
  }
  saveConfig({ byom: current } as RouteWiseConfig);
  return loadConfig();
}