/**
 * Small, dependency-free lexical highlighter. It colours tokens only; it never
 * alters or reflows source text, so line numbers stay exact.
 */
export type TokenKind =
  | "plain"
  | "keyword"
  | "string"
  | "comment"
  | "number"
  | "function"
  | "type"
  | "decorator"
  | "punct";

export interface Token {
  kind: TokenKind;
  text: string;
}

interface Grammar {
  keywords: ReadonlySet<string>;
  lineComments: readonly string[];
  blockComment: readonly [string, string] | null;
  tripleQuoteStrings: boolean;
  backtickStrings: boolean;
  decorators: boolean;
}

const words = (s: string): ReadonlySet<string> => new Set(s.split(/\s+/).filter(Boolean));

const PYTHON: Grammar = {
  keywords: words(
    "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield self cls match case",
  ),
  lineComments: ["#"],
  blockComment: null,
  tripleQuoteStrings: true,
  backtickStrings: false,
  decorators: true,
};

const TS: Grammar = {
  keywords: words(
    "abstract as async await break case catch class const continue debugger default delete do else enum export extends false finally for from function get if implements import in instanceof interface let new null of private protected public readonly return set static super switch this throw true try type typeof undefined var void while with yield keyof satisfies declare namespace",
  ),
  lineComments: ["//"],
  blockComment: ["/*", "*/"],
  tripleQuoteStrings: false,
  backtickStrings: true,
  decorators: true,
};

const JAVA: Grammar = {
  keywords: words(
    "abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null var record sealed permits yield",
  ),
  lineComments: ["//"],
  blockComment: ["/*", "*/"],
  tripleQuoteStrings: false,
  backtickStrings: false,
  decorators: true,
};

const GO: Grammar = {
  keywords: words(
    "break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var nil true false",
  ),
  lineComments: ["//"],
  blockComment: ["/*", "*/"],
  tripleQuoteStrings: false,
  backtickStrings: true,
  decorators: false,
};

const RUST: Grammar = {
  keywords: words(
    "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while",
  ),
  lineComments: ["//"],
  blockComment: ["/*", "*/"],
  tripleQuoteStrings: false,
  backtickStrings: false,
  decorators: false,
};

const C_LIKE: Grammar = {
  keywords: words(
    "auto break case char const continue default do double else enum extern float for goto if inline int long register return short signed sizeof static struct switch typedef union unsigned void volatile while class namespace template typename public private protected virtual override new delete true false nullptr using",
  ),
  lineComments: ["//"],
  blockComment: ["/*", "*/"],
  tripleQuoteStrings: false,
  backtickStrings: false,
  decorators: false,
};

const DATA: Grammar = {
  keywords: words("true false null yes no"),
  lineComments: ["#"],
  blockComment: null,
  tripleQuoteStrings: false,
  backtickStrings: false,
  decorators: false,
};

const GENERIC: Grammar = {
  keywords: words("if else for while return function class def import from true false null none"),
  lineComments: ["//", "#"],
  blockComment: ["/*", "*/"],
  tripleQuoteStrings: false,
  backtickStrings: false,
  decorators: false,
};

const BY_LANGUAGE: Record<string, Grammar> = {
  python: PYTHON,
  py: PYTHON,
  typescript: TS,
  tsx: TS,
  ts: TS,
  javascript: TS,
  jsx: TS,
  js: TS,
  java: JAVA,
  kotlin: JAVA,
  go: GO,
  rust: RUST,
  rs: RUST,
  c: C_LIKE,
  cpp: C_LIKE,
  "c++": C_LIKE,
  csharp: C_LIKE,
  json: DATA,
  yaml: DATA,
  yml: DATA,
  toml: DATA,
};

export function grammarFor(language: string | null): Grammar {
  return (language && BY_LANGUAGE[language.toLowerCase()]) || GENERIC;
}

const IDENT = /[A-Za-z_$][\w$]*/y;
const NUMBER = /(?:0[xXbBoO][\da-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)[jJlLfFuU]*/y;

function readQuoted(src: string, start: number, quote: string): number {
  let i = start + quote.length;
  const multiline = quote.length === 3 || quote === "`";
  while (i < src.length) {
    const ch = src[i];
    if (ch === "\\") {
      i += 2;
      continue;
    }
    if (src.startsWith(quote, i)) return i + quote.length;
    if (ch === "\n" && !multiline) return i;
    i += 1;
  }
  return src.length;
}

export function tokenize(src: string, language: string | null): Token[] {
  const g = grammarFor(language);
  const tokens: Token[] = [];
  const push = (kind: TokenKind, text: string): void => {
    const last = tokens[tokens.length - 1];
    if (last && last.kind === kind) last.text += text;
    else tokens.push({ kind, text });
  };

  let i = 0;
  while (i < src.length) {
    const ch = src[i] ?? "";

    if (g.blockComment && src.startsWith(g.blockComment[0], i)) {
      const end = src.indexOf(g.blockComment[1], i + g.blockComment[0].length);
      const stop = end === -1 ? src.length : end + g.blockComment[1].length;
      push("comment", src.slice(i, stop));
      i = stop;
      continue;
    }
    const lineComment = g.lineComments.find((c) => src.startsWith(c, i));
    if (lineComment) {
      const end = src.indexOf("\n", i);
      const stop = end === -1 ? src.length : end;
      push("comment", src.slice(i, stop));
      i = stop;
      continue;
    }
    if (g.tripleQuoteStrings && (src.startsWith('"""', i) || src.startsWith("'''", i))) {
      const stop = readQuoted(src, i, src.slice(i, i + 3));
      push("string", src.slice(i, stop));
      i = stop;
      continue;
    }
    if (ch === '"' || ch === "'" || (g.backtickStrings && ch === "`")) {
      const stop = readQuoted(src, i, ch);
      push("string", src.slice(i, stop));
      i = stop;
      continue;
    }
    if (g.decorators && ch === "@") {
      IDENT.lastIndex = i + 1;
      const m = IDENT.exec(src);
      if (m) {
        push("decorator", "@" + m[0]);
        i += 1 + m[0].length;
        continue;
      }
    }
    if (/\d/.test(ch)) {
      NUMBER.lastIndex = i;
      const m = NUMBER.exec(src);
      if (m) {
        push("number", m[0]);
        i += m[0].length;
        continue;
      }
    }
    IDENT.lastIndex = i;
    const ident = IDENT.exec(src);
    if (ident) {
      const word = ident[0];
      let j = i + word.length;
      while (src[j] === " ") j += 1;
      let kind: TokenKind = "plain";
      if (g.keywords.has(word)) kind = "keyword";
      else if (src[j] === "(") kind = "function";
      else if (/^[A-Z][A-Za-z0-9]*[a-z]/.test(word)) kind = "type";
      push(kind, word);
      i += word.length;
      continue;
    }
    push(/[{}()[\];,.:=<>+\-*/%!&|^~?]/.test(ch) ? "punct" : "plain", ch);
    i += 1;
  }
  return tokens;
}

/** Split a token stream into lines, preserving multi-line tokens across lines. */
export function tokenizeLines(src: string, language: string | null): Token[][] {
  const lines: Token[][] = [[]];
  for (const token of tokenize(src.replace(/\r\n?/g, "\n"), language)) {
    const parts = token.text.split("\n");
    parts.forEach((part, idx) => {
      if (idx > 0) lines.push([]);
      if (part) lines[lines.length - 1]?.push({ kind: token.kind, text: part });
    });
  }
  return lines;
}
