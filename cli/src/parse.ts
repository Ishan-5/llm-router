export interface ParsedArgs {
  command: string;
  positionals: string[];
  flags: Record<string, string | boolean>;
}

const VALUE_FLAGS = new Set([
  "tier",
  "threshold",
  "limit",
  "base-url",
  "base_url",
  "model",
  "provider",
  "max-tokens",
  "temperature",
  "timeout",
  "key",
]);

export function normalizeFlagName(name: string): string {
  return name.replace(/_/g, "-");
}

export function parseArgs(argv: string[]): ParsedArgs {
  let command = argv[0] ?? "help";
  let rest = argv.slice(1);
  if (command.startsWith("-")) {
    rest = [command, ...rest];
    command = "help";
  }
  const positionals: string[] = [];
  const flags: Record<string, string | boolean> = {};

  for (let i = 0; i < rest.length; i++) {
    const arg = rest[i];
    if (arg.startsWith("--")) {
      const eq = arg.indexOf("=");
      if (eq !== -1) {
        flags[normalizeFlagName(arg.slice(2, eq))] = arg.slice(eq + 1);
        continue;
      }
      const rawName = arg.slice(2);
      const name = normalizeFlagName(rawName);
      if (VALUE_FLAGS.has(name)) {
        const next = rest[i + 1];
        if (next === undefined || next.startsWith("-")) {
          throw new Error(`Missing value for --${name}`);
        }
        flags[name] = next;
        i++;
      } else {
        flags[name] = true;
      }
    } else if (arg.length > 1 && arg[0] === "-") {
      flags[normalizeFlagName(arg.slice(1))] = true;
    } else {
      positionals.push(arg);
    }
  }
  return { command, positionals, flags };
}

export function flagValue(flags: Record<string, string | boolean>, name: string): string | null {
  const v = flags[normalizeFlagName(name)];
  return typeof v === "string" ? v : null;
}

export function flagBool(flags: Record<string, string | boolean>, name: string): boolean {
  const v = flags[normalizeFlagName(name)];
  return v === true || v === "true" || v === "1";
}

export function validTier(value: string | null): "cheap" | "mid" | "frontier" | null {
  if (value === "cheap" || value === "mid" || value === "frontier") {
    return value;
  }
  return null;
}