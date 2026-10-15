import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { uiText } from "../src/uiText";
import SourceCitations from "../src/SourceCitations";

describe("persisted web sources", () => {
  it("shows the supplied title, snippet and real source URL", () => {
    const html = renderToStaticMarkup(
      <SourceCitations
        citations={[
          {
            source_label: "[W1] Public source",
            text: "Source excerpt",
            url: "https://example.org/assessment",
            kind: "web",
          },
        ]}
      />,
    );
    expect(html).toContain("[W1] Public source");
    expect(html).toContain("Source excerpt");
    expect(html).toContain('href="https://example.org/assessment"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("Retrieved web sources");
    expect(html).toContain('class="web-source-link"');
  });
  it("keeps existing course citations and rejects unsafe links", () => {
    const html = renderToStaticMarkup(
      <SourceCitations
        citations={[
          { source_label: "M17 worksheet" },
          { source_label: "Bad URL", url: "javascript:alert(1)" },
        ]}
      />,
    );
    expect(html).toContain("M17 worksheet");
    expect(html).not.toContain("href=");
  });
  it("uses English UI labels without translating supplied source titles", () => {
    const html = renderToStaticMarkup(
      <SourceCitations
        citations={[{ source_label: "[W1] 来源", url: "https://example.org" }]}
      />,
    );
    expect(html).toContain("Retrieved web sources");
    expect(html).toContain("[W1] 来源");
    expect(uiText("webSearchReady")).toContain("available in live mode");
  });
  it("does not invent a source panel when no source was cited", () => {
    expect(renderToStaticMarkup(<SourceCitations citations={[]} />)).toBe("");
  });
});
