import { createElement, type ReactNode } from "react";
import TeachingText from "./TeachingText";

type Part = string | { tag: string; props: Record<string, number>; children: Part[] };
const tags = new Set(["table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "ul", "ol", "li", "p", "br", "strong", "em", "b", "i"]);
const structural: Record<string, string[]> = { table: ["caption", "thead", "tbody", "tfoot", "tr"], thead: ["tr"], tbody: ["tr"], tfoot: ["tr"], tr: ["td", "th"], ul: ["li"], ol: ["li"] };
function decodeText(text: string) {
  const basic: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: "\u00a0" };
  return text.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (whole, entity: string) => {
    if (!entity.startsWith("#")) return basic[entity.toLowerCase()] ?? whole;
    const n = parseInt(entity.slice(entity[1].toLowerCase() === "x" ? 2 : 1), entity[1].toLowerCase() === "x" ? 16 : 10);
    return n > 0 && n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff) ? String.fromCodePoint(n) : whole;
  });
}
/** Parse only simple source-table markup. No DOM parser, URLs, event handlers,
 * styles or HTML execution. Any unsupported markup falls back to literal text. */
export function sourceTableParts(text: string): Part[] | null {
  if (!/<table(?:\s|>)/i.test(text)) return null;
  const tokens = text.match(/<[^>]*>|[^<]+/g) ?? [];
  if (tokens.join("") !== text || tokens.length > 12000) return null;
  const root: Part[] = [], stack: { tag: string; props: Record<string, number>; children: Part[] }[] = [];
  const append = (part: Part) => (stack.length ? stack[stack.length - 1].children : root).push(part);
  for (const token of tokens) {
    if (!token.startsWith("<")) {
      if (token.trim() && structural[stack.at(-1)?.tag ?? ""]) return null;
      if (token.trim() || !["table", "thead", "tbody", "tfoot", "tr"].includes(stack.at(-1)?.tag ?? "")) append(decodeText(token));
      continue;
    }
    const close = token.match(/^<\/([a-z]+)\s*>$/i);
    if (close) { if (stack.pop()?.tag !== close[1].toLowerCase()) return null; continue; }
    const open = token.match(/^<([a-z]+)([^>]*)>$/i);
    if (!open || !tags.has(open[1].toLowerCase())) return null;
    const tag = open[1].toLowerCase(), props: Record<string, number> = {};
    const permitted = structural[stack.at(-1)?.tag ?? ""];
    if (permitted && !permitted.includes(tag)) return null;
    let invalid = false;
    const rest = open[2].replace(/\s+(rowspan|colspan)\s*=\s*(?:"(\d+)"|'(\d+)'|(\d+))/gi, (_, attr: string, a?: string, b?: string, c?: string) => {
      const n = Number(a ?? b ?? c);if (!["td", "th"].includes(tag) || n < 1 || n > 99) invalid = true;
      props[attr.toLowerCase() === "rowspan" ? "rowSpan" : "colSpan"] = n;return "";
    }).trim();
    if (invalid || (rest && !(tag === "br" && rest === "/"))) return null;
    const node = { tag, props, children: [] as Part[] };append(node);
    if (tag !== "br") stack.push(node);
    if (stack.length > 24) return null;
  }
  return stack.length ? null : root;
}
function renderParts(parts: Part[], prefix = "source"): ReactNode[] {
  return parts.map((p, i) => {
    if (typeof p === "string") return p;
    let children = p.children;
    if (p.tag === "table") {
      children = [];let rows: Part[] = [];
      const flush = () => { if (rows.length) { children.push({ tag: "tbody", props: {}, children: rows });rows = []; } };
      for (const child of p.children) {
        if (typeof child !== "string" && child.tag === "tr") rows.push(child);
        else { flush();children.push(child); }
      }
      flush();
    }
    return createElement(p.tag, { ...p.props, key: `${prefix}-${i}` }, p.tag === "br" ? undefined : renderParts(children, `${prefix}-${i}`));
  });
}
export default function DocumentBlockContent({ text, format = "plain" }: { text: string; format?: "plain" | "markdown" }) {
  const parts = sourceTableParts(text);
  if (format === "markdown" && text && (!/<table(?:\s|>)/i.test(text) || parts)) {
    return <><div className="document-table-content">{parts ? parts.map((part, i) => typeof part === "string" ? <TeachingText key={i} sourceLineBreaks>{part}</TeachingText> : renderParts([part], `markdown-${i}`)) : <TeachingText sourceLineBreaks>{text}</TeachingText>}</div><details><summary>Raw transcription</summary><pre className="document-source-text">{text}</pre></details></>;
  }
  if (!parts) return <pre className="document-source-text">{text || "(No transcribed text)"}</pre>;
  return <><div className="document-table-content">{renderParts(parts)}</div><details><summary>Raw transcription</summary><pre className="document-source-text">{text}</pre></details></>;
}
