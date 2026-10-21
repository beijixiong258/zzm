// @vitest-environment happy-dom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import AnswerInput from "../src/vue/components/AnswerInput.vue";
import MaterialsPane from "../src/vue/components/MaterialsPane.vue";
import {
  answerFieldCount,
  answerIsComplete,
  parseAnswerFields,
  formatAnswerFields,
} from "../src/answer-fields";
import { newQuestion, worksheetReadbackMatches } from "../src/question-draft";
import {
  appendMaterialFiles,
  uploadMaterialQueue,
} from "../src/material-upload";
import { api } from "../src/api";
import { documentApi } from "../src/document-api";
import { setLocale, savedLocale } from "../src/i18n";
import { readRoute, routeHash } from "../src/routes";
import { fixtureWorkspace } from "./fixtures";
import {
  saveTeachingDraft,
  effectiveTeachingProfile,
} from "../src/teaching-profile";
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
  vi.restoreAllMocks();
  localStorage.clear();
  setLocale("en");
});
describe("usable answer fields without changing the answer API", () => {
  it("round-trips ordered slots and preserves spaces while typing", async () => {
    const q = {
      ...newQuestion("core", 1),
      type: "fill_in_blank" as const,
      answer_slots: 2,
    };
    wrapper = mount(AnswerInput, {
      props: {
        question: q,
        modelValue: "",
        "onUpdate:modelValue": (value: string) =>
          wrapper!.setProps({ modelValue: value }),
      },
    });
    await wrapper.findAll("input")[0].setValue("learning ");
    expect(wrapper.props("modelValue")).toBe("1. learning \n2. ");
    expect(answerIsComplete(q, wrapper.props("modelValue"))).toBe(false);
    await wrapper.findAll("input")[1].setValue("证据");
    const saved = wrapper.props("modelValue").trim();
    expect(answerIsComplete(q, saved)).toBe(true);
    expect(parseAnswerFields(saved, 2)).toEqual(["learning ", "证据"]);
    expect(formatAnswerFields(["", ""])).toBe("");
  });
  it("retains a legacy multi-line answer as editable text", () => {
    const q = {
      ...newQuestion("core", 1),
      type: "fill_in_blank" as const,
      answer_slots: 2,
    };
    const old = "原有答案，不按空位编号\n第二行保持原样";
    wrapper = mount(AnswerInput, { props: { question: q, modelValue: old } });
    expect(wrapper.get("textarea").element.value).toBe(old);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });
  it("matches each labelled image and locks read-only controls", () => {
    const q = {
      ...newQuestion("core", 1),
      type: "image_matching" as const,
      images: [
        { label: "甲", url: "/image-a", alt: "" },
        { label: "乙", url: "/image-b", alt: "" },
      ],
      options: ["过程", "结果"],
    };
    expect(answerFieldCount(q)).toBe(2);
    wrapper = mount(AnswerInput, {
      props: { question: q, modelValue: "1. 过程\n2. 结果", readonly: true },
    });
    expect(wrapper.findAll("select")).toHaveLength(2);
    expect(wrapper.findAll("select").every((el) => el.element.disabled)).toBe(
      true,
    );
    expect(wrapper.text()).toContain("甲");
  });
});
describe("material queue and save boundaries", () => {
  it("appends selections without losing successes or folder identity", () => {
    const a = new File(["a"], "same.txt", { lastModified: 1 });
    const b = new File(["b"], "same.txt", { lastModified: 1 });
    Object.defineProperty(a, "webkitRelativePath", { value: "甲/same.txt" });
    Object.defineProperty(b, "webkitRelativePath", { value: "乙/same.txt" });
    const initial = appendMaterialFiles([], [a]);
    initial[0].status = "uploaded";
    const rows = appendMaterialFiles(initial, [a, b]);
    expect(rows).toHaveLength(2);
    expect(rows[0].status).toBe("uploaded");
    expect(rows[1].relativePath).toBe("乙/same.txt");
  });
  it("shows the same effective answer-key privacy that the queue submits", async () => {
    vi.spyOn(documentApi, "capability").mockRejectedValue(
      new Error("preview only"),
    );
    wrapper = mount(MaterialsPane, {
      props: { materials: [], courseId: "synthetic" },
      attachTo: document.body,
      global: { stubs: { Teleport: true } },
    });
    await wrapper
      .findAll("button")
      .find((el) => el.text() === "Upload files")!
      .trigger("click");
    const file = new File(["source"], "key.txt");
    const input = wrapper.get("input[type=file]").element;
    Object.defineProperty(input, "files", { value: [file] });
    await wrapper.get("input[type=file]").trigger("change");
    const selects = wrapper.findAll("select");
    await selects[1].setValue("answer_key");
    expect(wrapper.findAll("select")[2].element.value).toBe("teacher");
    expect(wrapper.findAll("select")[4].element.value).toBe("teacher");
    expect(wrapper.findAll("select")[4].element.disabled).toBe(true);
    const upload = vi.fn(async () => ({
      id: "m",
      title: "key.txt",
      source_label: "key.txt",
      kind: "answer_key",
      visibility: "teacher" as const,
      status: "ready" as const,
      excerpt: "",
    }));
    await uploadMaterialQueue(
      "c",
      appendMaterialFiles([], [file]),
      { kind: "answer_key", visibility: "student" },
      () => {},
      () => true,
      upload,
    );
    expect(upload.mock.calls[0].slice(2, 4)).toEqual(["teacher", "answer_key"]);
    const material = {
      id: "saved",
      title: "key.txt",
      source_label: "key.txt",
      source_relative_path: "key.txt",
      kind: "answer_key",
      visibility: "teacher" as const,
      status: "ready" as const,
      excerpt: "",
    };
    const transport = vi.spyOn(api, "upload").mockResolvedValue(material);
    vi.spyOn(api, "courseMaterials").mockResolvedValue({
      materials: [{ ...material, session_ids: [] }],
    });
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Upload selected files")!
      .trigger("click");
    await flushPromises();
    expect(transport.mock.calls[0][6]).toBe("key.txt");
    expect(transport.mock.calls[0][7]).toBe("course");
    expect(wrapper.text()).toContain("1 file saved.");
    expect(
      wrapper.findAll("button").some((button) => button.text() === "Close"),
    ).toBe(true);
    expect(wrapper.emitted("libraryChanged")?.[0][0]).toEqual([
      { ...material, session_ids: [] },
    ]);
  });
  it("saves teaching fields independently of questions and rejects a wrong worksheet readback", async () => {
    const session = fixtureWorkspace().session;
    const draft = {
      ...session,
      teaching_profile: effectiveTeachingProfile(session),
    };
    const update = vi.spyOn(api, "updateSession").mockResolvedValue(draft);
    vi.spyOn(api, "session").mockResolvedValue(draft);
    await saveTeachingDraft(session.id, draft);
    expect(update.mock.calls[0][1]).not.toHaveProperty("questions");
    expect(update.mock.calls[0][1]).not.toHaveProperty("groups");
    const worksheet = {
      title: session.title,
      groups: session.groups,
      questions: session.questions,
      reference_answers: {},
    };
    expect(
      worksheetReadbackMatches(worksheet, {
        ...worksheet,
        questions: worksheet.questions.map((q, i) =>
          i === 0 ? { ...q, prompt: "wrong readback" } : q,
        ),
      }),
    ).toBe(false);
  });
});
it("preserves UI language and shallow course / tab context on reload", () => {
  setLocale("zh-CN");
  expect(savedLocale()).toBe("zh-CN");
  const r = {
    page: "teacher" as const,
    sid: "课次 A",
    course: "课程 B",
    tab: "materials",
    version: "v1",
  };
  expect(readRoute("#" + routeHash(r))).toEqual(r);
  expect(readRoute("#/home?course=two").course).toBe("two");
});
