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
    /* In-memory choice remains usable. */
  }
  if (typeof document !== "undefined")
    document.documentElement.lang = locale.value;
}

/** Only UI messages belong here. Course content and model responses stay verbatim. */
export function t(key: string, values: readonly unknown[] = []): string {
  const message = catalogs[locale.value][key] ?? key;
  // A callback keeps $&, braces and other user-supplied text literal.
  return message.replace(/\{(\d+)\}/g, (token, index: string) =>
    Number(index) < values.length ? String(values[Number(index)] ?? "") : token,
  );
}

/** Translate known server messages without hiding unfamiliar diagnostics. */
export function systemText(value: string): string {
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
  // Some existing API warnings concatenate sentences. Keep every unknown part.
  return value
    .split(/((?<=\.)\s*;?\s+(?=[A-Z0-9]))/g)
    .map((part, index) => (index % 2 ? part : translate(part)))
    .join("");
}

export function dateLocale() {
  return locale.value === "zh-CN" ? "zh-CN" : "en-US";
}
