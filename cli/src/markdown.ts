const BOLD = "\u001b[1m";
const DIM = "\u001b[2m";
const UNDERLINE = "\u001b[4m";
const CYAN = "\u001b[36m";
const RESET = "\u001b[0m";

const MAX_CELL = 60;

// Mirrors frontend/src/mathText.js. Models occasionally ignore the router's
// "no LaTeX" instruction; this turns common markup into readable text. Only
// delimited regions are expanded, then a whitelist of known math commands is
// replaced, so code samples (\n, \t) and currency ("costs $5") are untouched.
const MATH_COMMANDS: Record<string, string> = {
  times: "×", cdot: "·", div: "÷", pm: "±", mp: "∓",
  le: "≤", leq: "≤", ge: "≥", geq: "≥", ne: "≠", neq: "≠",
  approx: "≈", propto: "∝", infty: "∞", sum: "Σ", prod: "∏",
  int: "∫", partial: "∂", nabla: "∇", sqrt: "√", angle: "∠",
  circ: "°", deg: "°", prime: "′", perp: "⊥", parallel: "∥",
  equiv: "≡", cong: "≅", sim: "∼", simeq: "≃",
  in: "∈", notin: "∉", subset: "⊂", supset: "⊃", subseteq: "⊆", supseteq: "⊇",
  forall: "∀", exists: "∃", emptyset: "∅", therefore: "∴", because: "∵",
  langle: "⟨", rangle: "⟩",
  sin: "sin", cos: "cos", tan: "tan", cot: "cot", sec: "sec", csc: "csc",
  arcsin: "arcsin", arccos: "arccos", arctan: "arctan",
  sinh: "sinh", cosh: "cosh", tanh: "tanh",
  log: "log", ln: "ln", exp: "exp", lim: "lim", max: "max", min: "min",
  det: "det", gcd: "gcd", mod: "mod",
  rightarrow: "→", to: "→", Rightarrow: "⇒",
  leftarrow: "←", Leftarrow: "⇐",
  leftrightarrow: "↔", Leftrightarrow: "⇔",
  ldots: "…", cdots: "⋯", dots: "…", vdots: "⋮",
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", Delta: "Δ",
  epsilon: "ε", varepsilon: "ε", zeta: "ζ", eta: "η", theta: "θ",
  Theta: "Θ", iota: "ι", kappa: "κ", lambda: "λ", Lambda: "Λ",
  mu: "μ", nu: "ν", xi: "ξ", pi: "π", Pi: "Π", rho: "ρ", sigma: "σ",
  Sigma: "Σ", tau: "τ", upsilon: "υ", phi: "φ", varphi: "φ", chi: "χ",
  psi: "ψ", Psi: "Ψ", omega: "ω", Omega: "Ω",
};

function mathParen(s: string): string {
  return /[+\-/\s]/.test(s) ? `(${s})` : s;
}

// Structural + symbol replacements that are safe to run anywhere in a line.
function applyMathTokens(s: string): string {
  let out = s;
  out = out.replace(/\\begin\{[^}]*\}|\\end\{[^}]*\}/g, "");
  out = out.replace(/\\left|\\right/g, "");
  out = out.replace(
    /\\(?:boxed|text|mathrm|mathbf|mathit|operatorname)\s*\{([^{}]*)\}/g,
    "$1",
  );
  out = out.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (_m: string, a: string, b: string) =>
    `${mathParen(a)}/${mathParen(b)}`,
  );
  out = out.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
  out = out.replace(/\\(?:qquad|quad|,|;|:|!)/g, " ");
  out = out.replace(/\\([A-Za-z]+)/g, (m: string, name: string) =>
    Object.prototype.hasOwnProperty.call(MATH_COMMANDS, name) ? MATH_COMMANDS[name] : m,
  );
  out = out.replace(/\^\{([^{}]*)\}/g, "^$1");
  out = out.replace(/_\{([^{}]*)\}/g, "_$1");
  return out;
}

function convertMathRegion(expr: string): string {
  let out = applyMathTokens(expr);
  out = out.replace(/\\\\/g, " "); // LaTeX row break
  out = out.replace(/&=/g, "= ").replace(/\s*&\s*/g, " / "); // alignment columns
  return out.replace(/\s+/g, " ").trim();
}

export function cleanMath(text: string): string {
  if (!text) {
    return text;
  }
  return applyMathTokens(
    text
      .replace(/\$\$([\s\S]+?)\$\$/g, (_m: string, e: string) => convertMathRegion(e))
      .replace(/\\\[([\s\S]+?)\\\]/g, (_m: string, e: string) => convertMathRegion(e))
      .replace(/\\\(([\s\S]+?)\\\)/g, (_m: string, e: string) => convertMathRegion(e))
      .replace(/\$([^\s$\n](?:[^$\n]*[^\s$\n])?)\$/g, (_m: string, e: string) =>
        convertMathRegion(e),
      )
      // delimiters left behind by an unclosed region
      .replace(/\\\[|\\\]|\\\(|\\\)/g, ""),
  );
}

export interface FormatOptions {
  color: boolean;
}

function decorate(text: string, color: boolean): string {
  let out = text;
  out = out.replace(/`([^`\n]+)`/g, (_m, code: string) =>
    color ? CYAN + code + RESET : code,
  );
  out = out.replace(/\*\*([^*\n]+)\*\*/g, (_m, b: string) =>
    color ? BOLD + b + RESET : b,
  );
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)\]]+)\)/g, (_m, label: string, url: string) =>
    color ? `${label} (${CYAN}${url}${RESET})` : `${label} (${url})`,
  );
  return out;
}

function cellsOf(line: string): string[] {
  const parts = line
    .trim()
    .split("|")
    .map((s) => s.trim());
  if (parts[0] === "") {
    parts.shift();
  }
  if (parts[parts.length - 1] === "") {
    parts.pop();
  }
  return parts;
}

function isSeparatorRow(cells: string[]): boolean {
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}

function isTableRow(line: string): boolean {
  const t = line.trim();
  return t.startsWith("|") && t.endsWith("|") && t.split("|").length >= 3;
}

function renderTable(rows: string[][]): string[] {
  const data = rows.filter((r) => !isSeparatorRow(r));
  if (data.length === 0) {
    return [];
  }
  const firstData = rows.findIndex((r) => !isSeparatorRow(r));
  const header = firstData >= 0 && rows[firstData + 1] !== undefined && isSeparatorRow(rows[firstData + 1]);

  const colCount = Math.max(...data.map((r) => r.length));
  const widths: number[] = [];
  for (let ci = 0; ci < colCount; ci++) {
    let w = 0;
    for (const r of data) {
      w = Math.max(w, Math.min(MAX_CELL, (r[ci] ?? "").length));
    }
    widths.push(w);
  }

  const out: string[] = [];
  for (let ri = 0; ri < data.length; ri++) {
    const cells = data[ri];
    const line = cells
      .map((c, ci) => (c ?? "").padEnd(widths[ci]))
      .join("   ")
      .replace(/\s+$/, "");
    out.push(header && ri === 0 ? BOLD + line + RESET : line);
  }
  return out;
}

function transformLine(rawLine: string, color: boolean): string {
  const line = cleanMath(rawLine);
  const lead = line.match(/^\s*/)?.[0] ?? "";
  const trimmed = line.trim();
  if (trimmed === "") {
    return "";
  }

  const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
  if (heading) {
    const content = decorate(heading[2], color);
    if (!color) {
      return content;
    }
    return heading[1].length <= 2 ? BOLD + UNDERLINE + content + RESET : BOLD + content + RESET;
  }

  if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
    return color ? DIM + "  " + "─".repeat(40) + RESET : "  " + "─".repeat(40);
  }

  const quote = trimmed.match(/^>\s?(.*)$/);
  if (quote) {
    const content = decorate(quote[1], color);
    return color ? "  " + DIM + "│ " + content + RESET : "  │ " + content;
  }

  const checkbox = trimmed.match(/^[-*+]\s+\[( |x|X)\]\s+(.*)$/);
  if (checkbox) {
    const mark = checkbox[1] === " " ? "☐" : "☑";
    return lead + mark + " " + decorate(checkbox[2], color);
  }

  const bullet = trimmed.match(/^[-*+]\s+(.*)$/);
  if (bullet) {
    return lead + "• " + decorate(bullet[1], color);
  }

  const ordered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
  if (ordered) {
    return lead + ordered[1] + ". " + decorate(ordered[2], color);
  }

  return decorate(line.replace(/\s+$/, ""), color);
}

function collapseBlanks(lines: string[]): string[] {
  const out: string[] = [];
  let lastBlank = false;
  for (const l of lines) {
    if (l === "") {
      if (!lastBlank) {
        out.push("");
      }
      lastBlank = true;
    } else {
      out.push(l);
      lastBlank = false;
    }
  }
  while (out.length > 0 && out[out.length - 1] === "") {
    out.pop();
  }
  while (out.length > 0 && out[0] === "") {
    out.shift();
  }
  return out;
}

export function formatMarkdown(text: string, opts: FormatOptions): string {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let inCode = false;
  let tableBuf: string[][] = [];
  const out: string[] = [];

  const flushTable = (): void => {
    if (tableBuf.length > 0) {
      out.push("");
      out.push(...renderTable(tableBuf));
      out.push("");
      tableBuf = [];
    }
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (/^\s*(?:`{3,}|~{3,})/.test(line)) {
      flushTable();
      out.push("");
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      out.push((opts.color ? DIM : "") + "  " + line + (opts.color ? RESET : ""));
      continue;
    }
    if (isTableRow(line)) {
      tableBuf.push(cellsOf(line));
      continue;
    }
    flushTable();
    out.push(transformLine(line, opts.color));
  }
  flushTable();

  return collapseBlanks(out).join("\n") + "\n";
}

export interface StreamFormatState {
  pending: string;
  inCode: boolean;
}

export function createStreamState(): StreamFormatState {
  return { pending: "", inCode: false };
}

export function formatStreamChunk(
  chunk: string,
  state: StreamFormatState,
  opts: FormatOptions,
): string {
  state.pending += chunk;

  const cursor: string[] = [];
  while (true) {
    const nl = state.pending.indexOf("\n");
    if (nl === -1) {
      break;
    }
    const line = state.pending.slice(0, nl).replace(/\s+$/, "");
    state.pending = state.pending.slice(nl + 1);

    if (/^\s*(?:`{3,}|~{3,})/.test(line)) {
      state.inCode = !state.inCode;
      continue;
    }
    if (state.inCode) {
      cursor.push((opts.color ? DIM : "") + "  " + line + (opts.color ? RESET : ""));
    } else {
      cursor.push(transformLine(line, opts.color));
    }
  }

  // emit every complete line including blank (paragraph) breaks
  let out = "";
  for (const line of cursor) {
    out += line + "\n";
  }
  return out;
}

export function flushStream(state: StreamFormatState, opts: FormatOptions): string {
  const rest = state.pending.replace(/\s+$/, "");
  state.pending = "";
  if (!rest) {
    return "";
  }
  if (state.inCode) {
    return (opts.color ? DIM : "") + "  " + rest + (opts.color ? RESET : "");
  }
  return transformLine(rest, opts.color);
}