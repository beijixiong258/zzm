// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import WorksheetImporter from "../src/vue/components/WorksheetImporter.vue";
import { api } from "../src/api";
import type { SessionDetail, WorksheetPreview } from "../src/types";

let wrapper: VueWrapper | undefined;
const preview = {
  import_id: "synthetic-import",
  draft: {
    title: "Worksheet",
    groups: [],
    questions: [],
    reference_answers: {},
  },
  warnings: [],
  assets: [],
  method: "llm",
  needs_review: true,
} as unknown as WorksheetPreview;

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.restoreAllMocks();
});

describe("Worksheet import AI choice", () => {
  it("shows extraction warnings when no questions were returned", async () => {
    vi.spyOn(api, "worksheetFromMaterial").mockResolvedValue({
      ...preview,
      method: "error",
      warnings: ["Worksheet extraction failed; inspect the original file."],
    } as WorksheetPreview);
    wrapper = mount(WorksheetImporter, {
      props: {
        session: {
          id: "s4",
          materials: [
            { id: "worksheet", kind: "worksheet", title: "Worksheet" },
          ],
        } as unknown as SessionDetail,
      },
    });
    await wrapper.findAll("select")[1].setValue("worksheet");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain(
      "Worksheet extraction failed; inspect the original file.",
    );
    const save = wrapper
      .findAll("button")
      .find((button) => button.text() === "Save reviewed questions");
    expect(save?.attributes("disabled")).toBeDefined();
  });

  it.each([true, false])(
    "passes the AI choice for an uploaded worksheet: %s",
    async (useAi) => {
      const request = vi
        .spyOn(api, "worksheetPreview")
        .mockResolvedValue(preview);
      wrapper = mount(WorksheetImporter, {
        props: {
          session: { id: "s4", materials: [] } as unknown as SessionDetail,
        },
      });
      const checkbox = wrapper.get('input[type="checkbox"]');
      expect((checkbox.element as HTMLInputElement).checked).toBe(true);
      await checkbox.setValue(useAi);
      const file = new File(["Synthetic worksheet"], "worksheet.docx");
      const input = wrapper.get('input[type="file"]');
      Object.defineProperty(input.element, "files", {
        value: [file],
        configurable: true,
      });
      await input.trigger("change");
      await wrapper.get("form").trigger("submit");
      await flushPromises();
      expect(request).toHaveBeenCalledExactlyOnceWith("s4", file, useAi);
    },
  );

  it.each([true, false])(
    "passes the AI choice and answer source for saved materials: %s",
    async (useAi) => {
      const request = vi
        .spyOn(api, "worksheetFromMaterial")
        .mockResolvedValue(preview);
      const session = {
        id: "s4",
        materials: [
          {
            id: "worksheet",
            kind: "worksheet",
            title: "Worksheet",
            visibility: "teacher",
          },
          {
            id: "key",
            kind: "answer_key",
            title: "Private key",
            visibility: "teacher",
          },
        ],
      } as unknown as SessionDetail;
      wrapper = mount(WorksheetImporter, { props: { session } });
      const selects = wrapper.findAll("select");
      await selects[1].setValue("worksheet");
      await selects[2].setValue("key");
      await wrapper.get('input[type="checkbox"]').setValue(useAi);
      await wrapper.get("form").trigger("submit");
      await flushPromises();
      expect(request).toHaveBeenCalledExactlyOnceWith(
        "s4",
        "worksheet",
        "key",
        useAi,
      );
    },
  );
});
