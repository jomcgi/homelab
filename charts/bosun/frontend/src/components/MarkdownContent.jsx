import { useMemo, useCallback } from "react";
import { marked } from "marked";
import { C } from "../tokens.js";

// ── Markdown configuration ─────────────────────────────────────────────────
marked.setOptions({ breaks: true, gfm: true });

// Custom renderer: wrap code blocks with a copy button (no inline JS)
const renderer = new marked.Renderer();
renderer.code = function ({ text, lang }) {
  const escaped = encodeURIComponent(text);
  return `<div class="vcc-code-block" data-code="${escaped}"><button class="vcc-code-copy">Copy</button><pre><code class="language-${lang || ""}">${marked.parse(text).replace(/<\/?p>/g, "")}</code></pre></div>`;
};

export function MarkdownContent({ text }) {
  const html = useMemo(() => {
    if (!text) return "";
    return marked.parse(text, { renderer });
  }, [text]);

  // Delegated click handler — catches clicks on .vcc-code-copy buttons
  // without injecting JS into the HTML string.
  const handleClick = useCallback((e) => {
    const btn = e.target.closest(".vcc-code-copy");
    if (!btn) return;
    const block = btn.closest(".vcc-code-block");
    if (!block?.dataset.code) return;
    const code = decodeURIComponent(block.dataset.code);
    navigator.clipboard.writeText(code).then(() => {
      btn.textContent = "Copied";
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
    });
  }, []);

  return (
    <div
      className="vcc-markdown"
      dangerouslySetInnerHTML={{ __html: html }}
      onClick={handleClick}
      style={{ fontSize: 14, color: C.textSec, lineHeight: 1.6 }}
    />
  );
}
