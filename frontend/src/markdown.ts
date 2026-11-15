import { Marked } from "marked";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeHref(href: string): string | null {
  const trimmed = href.trim();
  if (/^(https?:|mailto:)/i.test(trimmed)) {
    return trimmed;
  }
  return null;
}

const marked = new Marked({
  gfm: true,
  renderer: {
    html({ text }) {
      return escapeHtml(text);
    },
    link({ href, title, text, tokens, autolink }) {
      const label = autolink ? escapeHtml(text) : this.parser.parseInline(tokens);
      const safe = safeHref(href);
      if (!safe) {
        return label;
      }
      const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
      return `<a href="${escapeHtml(safe)}"${titleAttr} target="_blank" rel="noopener">${label}</a>`;
    },
    image({ text, href }) {
      return escapeHtml(text || href);
    },
  },
});

export function renderMarkdown(source: string): string {
  return marked.parse(source, { async: false }) as string;
}
