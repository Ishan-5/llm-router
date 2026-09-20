const BOLD = "\u001b[1m";
const DIM = "\u001b[2m";
const UNDERLINE = "\u001b[4m";
const CYAN = "\u001b[36m";
const RESET = "\u001b[0m";

const MAX_CELL = 60;

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

function transformLine(line: string, color: boolean): string {
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