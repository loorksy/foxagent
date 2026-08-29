const KEYWORDS: Record<string, string[]> = {
  python: ["and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else", "except", "False", "for", "from", "global", "if", "import", "in", "is", "lambda", "None", "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield"],
  javascript: ["async", "await", "break", "case", "catch", "class", "const", "continue", "default", "else", "export", "for", "function", "if", "import", "let", "new", "return", "switch", "throw", "try", "typeof", "var", "void", "while", "yield"],
  typescript: ["async", "await", "break", "case", "catch", "class", "const", "continue", "default", "else", "export", "extends", "for", "function", "if", "import", "interface", "let", "new", "return", "switch", "type", "typeof", "var", "while"],
  pine: ["and", "export", "for", "if", "import", "not", "or", "series", "simple", "switch", "to", "type", "var", "varip", "while"],
  mql5: ["bool", "break", "case", "class", "const", "continue", "double", "else", "false", "for", "if", "input", "int", "new", "return", "string", "true", "void", "while"],
  sql: ["and", "as", "by", "from", "group", "inner", "insert", "into", "join", "left", "limit", "on", "or", "order", "select", "set", "update", "where"],
};

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function highlightCode(source: string, language: string): string {
  const lang = language.toLowerCase();
  if (lang === "json") {
    try {
      return escapeHtml(JSON.stringify(JSON.parse(source), null, 2))
        .replace(/(&quot;[^&]*&quot;)(?=\s*:)/g, '<span class="tok-key">$1</span>')
        .replace(/(:\s*)(&quot;[\s\S]*?&quot;)/g, '$1<span class="tok-str">$2</span>')
        .replace(/(:\s*)(-?\d+(?:\.\d+)?)/g, '$1<span class="tok-num">$2</span>');
    } catch {
      return escapeHtml(source);
    }
  }
  const words = KEYWORDS[lang] || KEYWORDS.javascript;
  const token = new RegExp(
    `(#.*$|//.*$|/\\*[\\s\\S]*?\\*/|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\`(?:\\\\.|[^\\\\\`])*\`|\\b(?:${words.join("|")})\\b|\\b\\d+(?:\\.\\d+)?\\b)`,
    "gm"
  );
  return escapeHtml(source).replace(token, (part) => {
    if (part.startsWith("#") || part.startsWith("//") || part.startsWith("/*")) {
      return `<span class="tok-cmt">${part}</span>`;
    }
    if (part.startsWith('"') || part.startsWith("'") || part.startsWith("`")) {
      return `<span class="tok-str">${part}</span>`;
    }
    if (/^\d/.test(part)) return `<span class="tok-num">${part}</span>`;
    return `<span class="tok-kw">${part}</span>`;
  });
}
