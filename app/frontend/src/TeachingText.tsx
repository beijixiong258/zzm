import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

type SourceNode = { type: string; value?: string; children?: SourceNode[] };
// Source Markdown tables commonly use <br> inside a cell. Admit that single
// presentation token as a Markdown break, never arbitrary raw HTML.
function sourceBreaks() {
  return (tree: SourceNode) => {
    const visit = (node: SourceNode) => {
      if (node.type === "html" && /^<br\s*\/?\s*>$/i.test(node.value ?? "")) { node.type = "break"; delete node.value; }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
}

/** Render teaching prose without executing raw HTML or loading model-supplied images. */
export default function TeachingText({ children, sourceLineBreaks = false }: { children: string; sourceLineBreaks?: boolean }) {
  return (
    <Markdown
      remarkPlugins={sourceLineBreaks ? [remarkGfm, sourceBreaks] : [remarkGfm]}
      skipHtml
      components={{
        a: ({ href, children }) =>
          href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ) : (
            <span>{children}</span>
          ),
        img: ({ alt }) => (
          <span className="markdown-image-label">{alt || "Image"}</span>
        ),
      }}
    >
      {children}
    </Markdown>
  );
}
