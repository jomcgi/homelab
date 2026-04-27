import { describe, it, expect } from "vitest";
import { renderMarkdown } from "./markdown.js";

describe("renderMarkdown", () => {
  const titleMap = new Map([["Existing Note", { id: "id-existing" }]]);

  it("renders headings", () => {
    expect(renderMarkdown("## hello", titleMap)).toContain("<h2>hello</h2>");
  });

  it("renders dash list items inside a single <ul>", () => {
    const html = renderMarkdown("- one\n- two", titleMap);
    expect(html).toMatch(/<ul>\s*<li>one<\/li>\s*<li>two<\/li>\s*<\/ul>/);
  });

  it("renders bold and italic", () => {
    const html = renderMarkdown("**bold** and *italic*", titleMap);
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<em>italic</em>");
  });

  it("renders inline code", () => {
    expect(renderMarkdown("use `foo`", titleMap)).toContain("<code>foo</code>");
  });

  it("renders blockquotes", () => {
    expect(renderMarkdown("> a quote", titleMap)).toContain("<blockquote>");
  });

  it("resolves wikilinks to live anchors", () => {
    const html = renderMarkdown("see [[Existing Note]]", titleMap);
    expect(html).toContain('class="wl"');
    expect(html).toContain('data-id="id-existing"');
  });

  it("renders unresolved wikilinks as dead links", () => {
    const html = renderMarkdown("see [[Missing]]", titleMap);
    expect(html).toContain('class="wl dead"');
    expect(html).not.toContain("data-id=");
  });

  it("escapes HTML in source", () => {
    expect(renderMarkdown("<script>", titleMap)).toContain("&lt;script&gt;");
  });

  it("preserves rendered tag spans through the escape pass", () => {
    const html = renderMarkdown(
      'foo <span class="tag">#x</span> bar',
      titleMap,
    );
    expect(html).toContain('<span class="tag">#x</span>');
    expect(html).not.toContain("&lt;span");
  });
});
