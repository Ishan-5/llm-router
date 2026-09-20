import { createInterface } from "node:readline/promises";
import type { JsonRecord, RouteWiseClient } from "./client.js";
import {
  createStreamState,
  flushStream,
  formatStreamChunk,
  type FormatOptions,
  type StreamFormatState,
} from "./markdown.js";

const HELP = [
  "Slash commands:",
  "  /help                                   show this help",
  "  /tier auto|cheap|mid|frontier           force a tier for following turns",
  "  /json on|off                            toggle raw JSON response output",
  "  /reset                                  clear conversation history",
  "  /exit, /quit                            leave the REPL",
].join("\n");

export interface ReplOptions {
  client: RouteWiseClient;
  model?: string;
  json?: boolean;
  color?: boolean;
  initialQuery?: string;
}

export async function startRepl(options: ReplOptions): Promise<number> {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  rl.setPrompt("routewise> ");
  let model = options.model ?? "auto";
  let jsonMode = options.json ?? false;
  const messages: Array<{ role: string; content: string }> = [];
  const fmt: FormatOptions = { color: Boolean(options.color) };

  console.log("routewise chat — multi-turn routing REPL. /help for commands.");

  const turn = async (input: string): Promise<void> => {
    messages.push({ role: "user", content: input });
    try {
      if (jsonMode) {
        const res = await options.client.chat({ messages, model });
        console.log(JSON.stringify(res, null, 2));
        return;
      }
      let full = "";
      const fmtState: StreamFormatState = createStreamState();
      for await (const chunk of options.client.chatStream({ messages, model })) {
        const choice = (chunk["choices"] as Array<JsonRecord> | undefined)?.[0];
        const delta = choice?.["delta"] as JsonRecord | undefined;
        const content = delta?.["content"];
        if (typeof content === "string" && content.length > 0) {
          full += content;
          const rendered = formatStreamChunk(content, fmtState, fmt);
          if (rendered.length > 0) {
            process.stdout.write(rendered);
          }
        }
      }
      const flushed = flushStream(fmtState, fmt);
      if (flushed.length > 0) {
        process.stdout.write(flushed);
      }
      if (full.length > 0) {
        process.stdout.write("\n");
      }
      messages.push({ role: "assistant", content: full || "(_no content_)" });
    } catch (err) {
      console.error(`routewise: ${(err as Error).message}`);
    }
  };

  if (options.initialQuery && options.initialQuery.trim()) {
    await turn(options.initialQuery.trim());
  }

  rl.prompt();

  for await (const line of rl) {
    const input = line.trim();
    if (!input) {
      rl.prompt();
      continue;
    }
    if (input.startsWith("/")) {
      const [cmd, ...rest] = input.slice(1).split(/\s+/);
      const arg = rest.join(" ");
      if (cmd === "exit" || cmd === "quit") {
        break;
      }
      if (cmd === "help") {
        console.log(HELP);
      } else if (cmd === "reset") {
        messages.length = 0;
        console.log("Conversation reset.");
      } else if (cmd === "tier") {
        const t = arg.trim();
        if (["auto", "cheap", "mid", "frontier"].includes(t)) {
          model = t;
          console.log(`Tier set to ${t}.`);
        } else {
          console.log("Tier must be auto, cheap, mid, or frontier.");
        }
      } else if (cmd === "json") {
        jsonMode = arg === "on" || arg === "true";
        console.log(`JSON output ${jsonMode ? "on" : "off"}.`);
      } else {
        console.log(`Unknown command: /${cmd}. Type /help.`);
      }
      rl.prompt();
      continue;
    }

    await turn(input);
    rl.prompt();
  }

  console.log("\nbye.");
  return 0;
}