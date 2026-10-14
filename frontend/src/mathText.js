// Models occasionally ignore the router's "no LaTeX" instruction. This turns
// the common math markup into readable plain text so it never renders as
// literal backslashes in the dashboard.
//
// Safety rules, because this runs over the whole Markdown string:
//   * delimited math regions ($$..$$, \[..\], \(..\), $..$) are expanded fully;
//   * then a WHITELIST of known math commands (\frac, \alpha, \times, ...) is
//     rewritten anywhere it appears -- unknown commands such as \n or \t are
//     left untouched so code samples survive;
//   * inline $..$ requires no space just inside the delimiters, so ordinary
//     currency ("costs $5 and $10") is never mistaken for math.
//
// The CLI mirrors this in cli/src/markdown.ts; keep the two in step.

const MATH_COMMANDS = {
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

function mathParen(s) {
  return /[+\-/\s]/.test(s) ? `(${s})` : s;
}

// Structural + symbol replacements that are safe to run anywhere in a line.
function applyMathTokens(s) {
  let out = s;
  out = out.replace(/\\begin\{[^}]*\}|\\end\{[^}]*\}/g, "");
  out = out.replace(/\\left|\\right/g, "");
  out = out.replace(
    /\\(?:boxed|text|mathrm|mathbf|mathit|operatorname)\s*\{([^{}]*)\}/g,
    "$1",
  );
  out = out.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (_m, a, b) =>
    `${mathParen(a)}/${mathParen(b)}`,
  );
  out = out.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
  out = out.replace(/\\(?:qquad|quad|,|;|:|!)/g, " ");
  out = out.replace(/\\([A-Za-z]+)/g, (m, name) =>
    MATH_COMMANDS[name] !== undefined ? MATH_COMMANDS[name] : m,
  );
  out = out.replace(/\^\{([^{}]*)\}/g, "^$1");
  out = out.replace(/_\{([^{}]*)\}/g, "_$1");
  return out;
}

function convertMathRegion(expr) {
  let out = applyMathTokens(expr);
  out = out.replace(/\\\\/g, " "); // LaTeX row break
  out = out.replace(/&=/g, "= ").replace(/\s*&\s*/g, " / "); // alignment columns
  return out.replace(/\s+/g, " ").trim();
}

export function prettifyMath(text) {
  if (!text) {
    return text;
  }
  return applyMathTokens(
    text
      .replace(/\$\$([\s\S]+?)\$\$/g, (_m, e) => convertMathRegion(e))
      .replace(/\\\[([\s\S]+?)\\\]/g, (_m, e) => convertMathRegion(e))
      .replace(/\\\(([\s\S]+?)\\\)/g, (_m, e) => convertMathRegion(e))
      .replace(/\$([^\s$\n](?:[^$\n]*[^\s$\n])?)\$/g, (_m, e) =>
        convertMathRegion(e),
      )
      // delimiters left behind by an unclosed region
      .replace(/\\\[|\\\]|\\\(|\\\)/g, ""),
  );
}
