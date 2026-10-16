// @vitest-environment happy-dom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { nextTick } from "vue";
import en from "../src/locales/en.json";
import zh from "../src/locales/zh-CN.json";
import { locale, setLocale, systemText, t } from "../src/i18n";
import { dateText } from "../src/vue/utils";
import QuestionManager from "../src/vue/components/QuestionManager.vue";
import LanguageSelect from "../src/vue/components/LanguageSelect.vue";
import LoginView from "../src/vue/views/LoginView.vue";
import { newQuestion } from "../src/question-draft";
import type { WorksheetDraft } from "../src/types";

const wrappers: VueWrapper[] = [];
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount());
  setLocale("en");
});

describe("shared bilingual interface", () => {
  it("keeps complete catalogs with the same interpolation arguments", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zh).sort());
    for (const [key, value] of Object.entries(zh)) {
      expect(value.trim(), key).not.toBe("");
      expect((value.match(/\{\d+\}/g) ?? []).sort(), key).toEqual(
        (key.match(/\{\d+\}/g) ?? []).sort(),
      );
    }
  });

  it("preserves user data in interpolation and unknown diagnostics", () => {
    setLocale("zh-CN");
    const name = "Name $& {1} <img src=x>";
    expect(t("Remove {0} from this course?", [name])).toBe(
      `将 ${name} 从本课程移除？`,
    );
    expect(systemText("Email or password is incorrect")).toBe(
      "邮箱或密码不正确",
    );
    expect(systemText("Provider diagnostic 9ab: unavailable")).toBe(
      "Provider diagnostic 9ab: unavailable",
    );
  });

  it("uses the active locale for page language and dates", () => {
    const input = "2026-10-16T04:05:00Z";
    for (const language of ["zh-CN", "en"] as const) {
      setLocale(language);
      expect(document.documentElement.lang).toBe(language);
      expect(dateText(input)).toBe(
        new Date(input).toLocaleString(language === "en" ? "en-GB" : "zh-CN", {
          dateStyle: "medium",
          timeStyle: "short",
        }),
      );
    }
    setLocale("invalid");
    expect(locale.value).toBe("en");
  });

  it("localizes combined server warnings while retaining counts and unknown details", () => {
    const warning =
      "10 extraction unit(s) failed; inspect failed_units and the retained original. Provider diagnostic 9ab: unavailable";
    setLocale("zh-CN");
    expect(systemText(warning)).toBe(
      "有 10 个提取单元失败，请查看 failed_units 并核对保留的原件。 Provider diagnostic 9ab: unavailable",
    );
    setLocale("en");
    expect(systemText(warning)).toBe(warning);
  });

  it("does not capture earlier warning sentences as a numeric parameter", () => {
    setLocale("zh-CN");
    const text =
      "CPU OCR recognizes raster text, not diagram/chart relationships, color coding, handwriting accuracy or complete visual meaning; compare with the original. 8 extraction unit(s) failed; inspect failed_units and the retained original.";
    const translated = systemText(text);
    expect(translated).toContain("CPU OCR 仅识别图片中的文字");
    expect(translated).toContain("有 8 个提取单元失败");
    expect(translated).not.toContain("有 CPU OCR");
    expect(translated).not.toContain("recognizes raster");
    expect(
      systemText(
        text +
          " No extractable text was found; OCR is not proof of an empty document. Teacher inspection is required.",
      ),
    ).toContain("未提取到文字，这并不代表文档为空。 请教师检查原件。");
  });

  it("switches the login interface without replacing entered credentials", async () => {
    setLocale("zh-CN");
    const view = mount(LoginView, { props: { bootstrap: null } });
    wrappers.push(view);
    expect(view.text()).toContain("登录工作区");
    await view.get('input[type="email"]').setValue("local@example.test");
    await view.get('input[type="password"]').setValue("Synthetic123");
    await view.get("select.language-select").setValue("en");
    expect(view.text()).toContain("Sign in to your workspace");
    expect(
      (view.get('input[type="email"]').element as HTMLInputElement).value,
    ).toBe("local@example.test");
    expect(
      (view.get('input[type="password"]').element as HTMLInputElement).value,
    ).toBe("Synthetic123");
  });

  it("preserves course text, answer keys, identifiers and unsaved edits across languages", async () => {
    const value: WorksheetDraft = {
      title: "English source",
      groups: [{ id: "core", kind: "core", title: "Original group" }],
      questions: [{ ...newQuestion("core", 1), id: "q1", prompt: "Save" }],
      reference_answers: { q1: "Original answer" },
    };
    const original = structuredClone(value);
    const save = vi.fn(async () => {});
    setLocale("zh-CN");
    const view = mount(QuestionManager, {
      props: { value, materials: [], save },
      global: { stubs: { Teleport: true } },
      attachTo: document.body,
    });
    const picker = mount(LanguageSelect, {
      global: { stubs: { Teleport: true } },
    });
    wrappers.push(view, picker);
    expect(view.text()).toContain("Original group");
    expect(view.text()).toContain("Save");
    expect(view.text()).toContain("新增题目");
    const edit = view.findAll("button").find((b) => b.text() === "修改")!;
    await edit.trigger("click");
    expect(view.text()).toContain("修改题目");
    await view
      .get('textarea[placeholder="输入学生将看到的题目…"]')
      .setValue("English revised prompt");
    await picker.get("select").setValue("en");
    await nextTick();
    expect(view.text()).toContain("Edit question");
    expect(
      (
        view.get(
          'textarea[placeholder="Write the question students will see…"]',
        ).element as HTMLTextAreaElement
      ).value,
    ).toBe("English revised prompt");
    expect(value).toEqual(original);
    await view.get("#question-editor").trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledOnce();
    const saved = (save.mock.calls as unknown as [WorksheetDraft][])[0][0];
    expect(saved.questions[0].type).toBe("open_response");
    expect(saved.questions[0].id).toBe("q1");
    expect(saved.reference_answers).toEqual(original.reference_answers);
    expect(saved.groups).toEqual(original.groups);
    expect(saved.questions[0].prompt).toBe("English revised prompt");
  });
});
