export const instructionLimit = 30000;
export function combineInstructions(
  current: string,
  imported: string,
  mode: "append" | "replace",
): string {
  return mode === "replace"
    ? imported
    : current && imported
      ? `${current}\n\n${imported}`
      : current + imported;
}
