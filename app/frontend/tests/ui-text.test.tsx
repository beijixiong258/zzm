import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { uiText } from "../src/uiText";
import { AiBadge, Brand } from "../src/ui";
import Materials from "../src/Materials";
describe("English-only UI and disclosure", () => {
  it("renders the AIcademiya brand and English tagline without locale controls", () => {
    const html = renderToStaticMarkup(<Brand />);
    expect(html).toContain("AIcademiya");
    expect(html).toContain("LEARN WITH INTENTION");
    expect(html).not.toMatch(/Akademiya|locale-button|[\u4e00-\u9fff]/);
  });
  it("has English navigation and submission labels", () => {
    for (const key of [
      "home",
      "history",
      "settings",
      "submit",
      "confirmed",
      "reference",
      "demo",
    ] as const) {
      expect(uiText(key)).toMatch(/[A-Za-z]/);
      expect(uiText(key)).not.toMatch(/[\u4e00-\u9fff]/);
    }
  });
  it("labels deterministic feedback as not a model", () => {
    const html = renderToStaticMarkup(
      <AiBadge
        ai={{ mode: "demo", configured: true, base_url: "", model: "demo" }}
        detail
      />,
    );
    expect(html).toContain("Development fixture");
    expect(html).toContain("Test fixture");
    expect(html).not.toContain("Last check passed");
    expect(html).not.toContain("Active AI Model");
  });
  it("renders English live-model and configuration disclosures", () => {
    const html = renderToStaticMarkup(
      <AiBadge
        ai={{ mode: "openai", configured: false, base_url: "", model: "" }}
        detail
      />,
    );
    expect(html).toContain("Active AI Model");
    expect(html).toContain("Not configured");
  });
  it("hides teacher-only material even if a malformed student payload includes it", () => {
    const html = renderToStaticMarkup(
      <Materials
        materials={[
          {
            id: "private",
            title: "PRIVATE TEACHER FIXTURE",
            visibility: "teacher",
            source_label: "Synthetic test",
            kind: "answer_key",
            status: "ready",
            excerpt: "SENSITIVE TEST MARKER",
          },
        ]}
      />,
    );
    expect(html).not.toContain("SENSITIVE TEST MARKER");
    expect(html).not.toContain("PRIVATE TEACHER FIXTURE");
  });
});
