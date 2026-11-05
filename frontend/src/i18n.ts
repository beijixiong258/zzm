import { ref } from "vue";
import en from "./locales/en.json";
import zh from "./locales/zh-CN.json";

export type Locale = "en" | "zh-CN";
export const locale = ref<Locale>(savedLocale() || "zh-CN");
const catalogs: Record<Locale, Record<string, string>> = { en, "zh-CN": zh };
const englishByChinese = new Map(
  Object.entries(zh).map(([key, text]) => [text, key]),
);
const escapePattern = (text: string) =>
  text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const numericServerMessages = new Set([
  "Page {0}",
  "Slide {0}",
  "Image {0}",
  "Sheet {0}",
  "Office graphic {0}",
  "Equation {0}",
  "Text box {0}",
  "{0} extraction unit(s) failed; inspect failed_units and the retained original.",
  "{0} introductory/unassigned text blocks remain in source_text, not automatically converted into questions.",
  "Request failed ({0})",
  "Upload failed ({0})",
]);
const systemPatterns = Object.entries(en).flatMap(([key]) => {
  if (!numericServerMessages.has(key)) return [];
  return [key, (zh as Record<string, string>)[key]].map((text) => {
    const indexes: number[] = [];
    const pattern = text
      .split(/(\{\d+\})/g)
      .map((part) => {
        if (/^\{\d+\}$/.test(part)) {
          indexes.push(Number(part.slice(1, -1)));
          return "(\\d+)";
        }
        return escapePattern(part);
      })
      .join("");
    return { key, indexes, pattern: new RegExp(`^${pattern}$`) };
  });
});

export function savedLocale(): Locale | null {
  try {
    const value = localStorage.getItem("aicademiya.ui-locale");
    return value === "en" || value === "zh-CN" ? value : null;
  } catch {
    return null;
  }
}
export function setLocale(value: string) {
  locale.value = value === "zh-CN" ? "zh-CN" : "en";
  try {
    localStorage.setItem("aicademiya.ui-locale", locale.value);
  } catch {
    /* 仍可使用保存在内存中的选择。 */
  }
  if (typeof document !== "undefined")
    document.documentElement.lang = locale.value;
}

/** 此处只翻译界面消息，课程内容和模型响应保持原文。 */
export function t(key: string, values: readonly unknown[] = []): string {
  const message = catalogs[locale.value][key] ?? key;
  // 使用回调，保留用户文本中的 $&、花括号等内容的原始含义。
  return message.replace(/\{(\d+)\}/g, (token, index: string) =>
    Number(index) < values.length ? String(values[Number(index)] ?? "") : token,
  );
}

/** 翻译已知的服务端消息，保留无法识别的诊断信息。 */
export function systemText(value: string): string {
  const question = value.match(/^Question (\d+): ([\s\S]*)$/);
  if (question)
    return t("Question {0}", [question[1]]) + ": " + systemText(question[2]);
  const upstream = value.match(
    /^Upstream AI request failed \(HTTP (\d+)\): ([\s\S]*)$/,
  );
  if (upstream)
    return (
      t("Upstream AI request failed (HTTP {0})", [upstream[1]]) +
      ": " +
      systemText(upstream[2])
    );
  for (const prefix of [
    "Material preparation failed",
    "Model output parsing failed",
    "Question validation failed",
    "AI request failed",
    "Material is used by tasks. Remove its references or archive it",
  ]) {
    if (value.startsWith(prefix + ": "))
      return t(prefix) + ": " + systemText(value.slice(prefix.length + 2));
  }
  const translate = (part: string): string => {
    if (Object.hasOwn(en, part)) return t(part);
    const english = englishByChinese.get(part);
    if (english) return t(english);
    for (const item of systemPatterns) {
      const match = part.match(item.pattern);
      if (!match) continue;
      const values: string[] = [];
      item.indexes.forEach((index, capture) => {
        values[index] = match[capture + 1];
      });
      return t(item.key, values);
    }
    return part;
  };
  const whole = translate(value);
  if (whole !== value) return whole;
  // 部分已有接口警告由多个句子拼接而成，保留所有无法识别的部分。
  return value
    .split(/((?<=\.)\s*;?\s+(?=[A-Z0-9]))/g)
    .map((part, index) => (index % 2 ? part : translate(part)))
    .join("");
}

export function dateLocale() {
  return locale.value === "zh-CN" ? "zh-CN" : "en-US";
}
