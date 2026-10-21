import type { Question } from "./types";
export function answerFieldCount(q: Question): number {
  return Math.max(
    1,
    Math.min(
      100,
      q.type === "image_matching" && q.images.length
        ? q.images.length
        : q.answer_slots || 1,
    ),
  );
}
export function parseAnswerFields(
  value: string,
  count: number,
): string[] | null {
  if (!value.trim()) return Array(count).fill("");
  if (count === 1 && !value.startsWith("1. "))
    return value.includes("\n") ? null : [value];
  const lines = value.split("\n");
  if (
    lines.length !== count ||
    lines.some((line, i) => !line.startsWith(`${i + 1}. `))
  )
    return null;
  return lines.map((line, i) => line.slice(`${i + 1}. `.length));
}
export function formatAnswerFields(values: string[]): string {
  if (!values.some((value) => value.trim())) return "";
  return values.map((value, i) => `${i + 1}. ${value}`).join("\n");
}
export function answerIsComplete(q: Question, value: string): boolean {
  if (!["fill_in_blank", "image_matching"].includes(q.type))
    return !!value.trim();
  const fields = parseAnswerFields(value, answerFieldCount(q));
  return fields ? fields.every((field) => !!field.trim()) : !!value.trim();
}
