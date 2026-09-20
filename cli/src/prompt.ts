import readline from "node:readline";

export async function promptHidden(question: string): Promise<string> {
  return new Promise((resolve) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: true,
    });
    const write = process.stdout.write.bind(process.stdout);
    readline.emitKeypressEvents(process.stdin, rl);
    process.stdin.setRawMode?.(true);
    process.stdout.write(question);

    let value = "";
    const finish = (result: string): void => {
      process.stdin.setRawMode?.(false);
      process.stdout.write("\n");
      rl.close();
      resolve(result);
    };
    const clean = (): void => {
      write(`\x1b[2K\r${question}${"*".repeat(value.length)}`);
    };

    process.stdin.on(
      "keypress",
      (
        char: string | undefined,
        key: { name: string; ctrl: boolean; meta: boolean },
      ) => {
        if (key.ctrl && key.name === "c") {
          finish(value);
          process.exit(1);
        }
        if (key.name === "return" || key.name === "enter") {
          finish(value.trim());
          return;
        }
        if (key.name === "backspace") {
          value = value.slice(0, -1);
          clean();
          return;
        }
        if (char && !key.ctrl && !key.meta) {
          value += char;
          write("*");
        }
      },
    );
  });
}