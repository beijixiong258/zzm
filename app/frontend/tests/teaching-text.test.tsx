import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import TeachingText from "../src/TeachingText";

describe("teaching response formatting", () => {
  it("renders the emphasis and lists observed in real model responses", () => {
    const html = renderToStaticMarkup(
      <TeachingText>
        {"The reference is **practicality**.\n\n- Time\n- Resources"}
      </TeachingText>,
    );
    expect(html).toContain("<strong>practicality</strong>");
    expect(html).toContain("<ul>");
    expect(html).not.toContain("**practicality**");
  });
  it("does not run HTML, unsafe links or load model-supplied remote images", () => {
    const html = renderToStaticMarkup(
      <TeachingText>
        {
          "<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))\n\n![diagram](https://example.invalid/tracker.png)"
        }
      </TeachingText>,
    );
    expect(html).not.toContain("<script");
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain("<img");
    expect(html).not.toContain('rel="preload"');
    expect(html).toContain("diagram");
  });
});
