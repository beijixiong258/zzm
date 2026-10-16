// @vitest-environment happy-dom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import QuestionManager from "../src/vue/components/QuestionManager.vue";
import { confirmation, resolveConfirm } from "../src/vue/state";
import type { WorksheetDraft } from "../src/types";
import { newQuestion } from "../src/question-draft";
let wrapper: VueWrapper | undefined;
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  resolveConfirm(false);
  vi.restoreAllMocks();
});
function setup() {
  const value: WorksheetDraft = {
    title: "Synthetic worksheet",
    groups: [{ id: "core", kind: "core", title: "Core", description: "" }],
    questions: [
      {
        ...newQuestion("core", 1),
        id: "q1",
        prompt: "Explain the source evidence.",
        source_material_ids: ["m1"],
      },
    ],
    reference_answers: { q1: "Private answer" },
  };
  const save = vi.fn(async (next: WorksheetDraft) => {
    await wrapper!.setProps({ value: next });
  });
  wrapper = mount(QuestionManager, {
    props: { value, materials: [], save },
    global: { stubs: { Teleport: true } },
    attachTo: document.body,
  });
  return { save, value };
}
function button(text: string) {
  const found = wrapper!.findAll("button").find((b) => b.text() === text);
  if (!found) throw Error(`Missing control: ${text}`);
  return found;
}
function promptField() {
  return wrapper!.get(
    'textarea[placeholder="Write the question students will see…"]',
  );
}
describe("Vue question management", () => {
  it("opens one add form and saves a new row once", async () => {
    const { save } = setup();
    expect(wrapper!.find("form").exists()).toBe(false);
    await button("Add question").trigger("click");
    await promptField().setValue("Compare two interpretations.");
    await wrapper!.get("#question-editor").trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].questions).toHaveLength(2);
    expect(wrapper!.find("form").exists()).toBe(false);
    expect(wrapper!.text()).toContain("Compare two interpretations.");
  });
  it("discards a cancelled edit without changing the saved question", async () => {
    const { save, value } = setup();
    const native = vi.spyOn(window, "confirm");
    await button("Edit").trigger("click");
    await promptField().setValue("Do not persist this edit.");
    await button("Cancel").trigger("click");
    expect(wrapper!.text()).toContain("Discard unsaved changes?");
    await button("Discard changes").trigger("click");
    await flushPromises();
    expect(save).not.toHaveBeenCalled();
    expect(value.questions[0].prompt).toBe("Explain the source evidence.");
    expect(native).not.toHaveBeenCalled();
  });
  it("retains source bindings and private reference text when editing", async () => {
    const { save } = setup();
    await button("Edit").trigger("click");
    await promptField().setValue("Explain and compare.");
    await wrapper!.get("#question-editor").trigger("submit");
    await flushPromises();
    const next = save.mock.calls[0][0];
    expect(next.questions[0].source_material_ids).toEqual(["m1"]);
    expect(next.reference_answers.q1).toBe("Private answer");
  });
  it("keeps the editor and entered text after a server rejection", async () => {
    const { save } = setup();
    save.mockRejectedValueOnce(new Error("Synthetic conflict"));
    await button("Edit").trigger("click");
    await promptField().setValue("Retain the unsaved correction.");
    await wrapper!.get("#question-editor").trigger("submit");
    await flushPromises();
    expect(wrapper!.text()).toContain("Synthetic conflict");
    expect((promptField().element as HTMLTextAreaElement).value).toBe(
      "Retain the unsaved correction.",
    );
  });
  it("confirms deletion inside the app and removes its private answer", async () => {
    const { save } = setup();
    const native = vi.spyOn(window, "confirm");
    await button("Delete").trigger("click");
    expect(confirmation.value?.message).toContain(
      "Explain the source evidence.",
    );
    expect(save).not.toHaveBeenCalled();
    resolveConfirm(true);
    await flushPromises();
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].questions).toEqual([]);
    expect(save.mock.calls[0][0].reference_answers).toEqual({});
    expect(native).not.toHaveBeenCalled();
  });
});
