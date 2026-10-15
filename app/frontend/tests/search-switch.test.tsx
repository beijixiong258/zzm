import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import SearchToggle, { webSearchAvailable } from "../src/SearchToggle";

import type { AiStatus } from "../src/types";
const live: AiStatus = {
  mode: "openai",
  configured: true,
  base_url: "",
  model: "fixture",
  web_search: { enabled: true, configured: true, provider: "tavily" },
};

describe("learner/teacher search switch", () => {
  it("renders an accessible switch with explicit on/off state", () => {
    const off = renderToStaticMarkup(
      <SearchToggle ai={live} value={false} onChange={() => {}} />,
    );
    const on = renderToStaticMarkup(
      <SearchToggle ai={live} value onChange={() => {}} />,
    );
    expect(off).toContain('role="switch"');
    expect(off).toContain('aria-label="Web search"');
    expect(off).toContain('aria-checked="false"');
    expect(on).toContain('aria-checked="true"');
    expect(on).not.toContain('disabled=""');
  });
  it("does not suggest a demo conversation will perform a real search", () => {
    const html = renderToStaticMarkup(
      <SearchToggle ai={{ ...live, mode: "demo" }} value onChange={() => {}} />,
    );
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-checked="false"');
    expect(html).toContain("Demo mode does not search");
  });
  it("disables the switch when the server capability/key is unavailable", () => {
    expect(webSearchAvailable(undefined)).toBe(false);
    expect(webSearchAvailable({ ...live, web_search: undefined })).toBe(false);
    expect(
      webSearchAvailable({
        ...live,
        web_search: { enabled: true, configured: false, provider: "tavily" },
      }),
    ).toBe(false);
    expect(
      webSearchAvailable({
        ...live,
        web_search: { enabled: false, configured: true, provider: "tavily" },
      }),
    ).toBe(false);
    expect(webSearchAvailable(live)).toBe(true);
  });
  it("uses English labels and disables changes while a request is pending", () => {
    const html = renderToStaticMarkup(
      <SearchToggle ai={live} value disabled onChange={() => {}} />,
    );
    expect(html).toContain('aria-label="Web search"');
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain('disabled=""');
  });
});
