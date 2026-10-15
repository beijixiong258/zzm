import { describe, expect, it } from "vitest";
import {
  combineInstructions,
  instructionLimit,
} from "../../src/teacher-workbench-import";
import {
  composerEnterAction,
  conversationScope,
  pendingKey,
  sameTurn,
  acknowledgePending,
  storePending,
  readPending,
} from "../../src/guided-study";
import { draftKey, writeDraft, readDraft } from "../../src/drafts";
import type { Workspace } from "../../src/types";
const workspace = (id: string): Workspace =>
  ({
    user: { id: "teacher" },
    session: { id: "s1" },
    version: { id: null, is_draft: true },
    preview: { id },
    tutor: { current_question_id: "q1" },
  }) as Workspace;
const storage = () => {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
    removeItem: (k: string) => {
      map.delete(k);
    },
  };
};
describe("teacher workbench import", () => {
  it("explicit append preserves current text, no trimming", () =>
    expect(combineInstructions("existing\n", " imported ", "append")).toBe(
      "existing\n\n\n imported ",
    ));
  it("replace only returns reviewed text", () =>
    expect(combineInstructions("existing", "new", "replace")).toBe("new"));
  it("counts separator toward 30000 without truncation", () => {
    const text = combineInstructions(
      "x".repeat(instructionLimit - 1),
      "y",
      "append",
    );
    expect(text.length).toBe(30002);
    expect(text.endsWith("\n\ny")).toBe(true);
  });
  it("empty append is lossless", () =>
    expect(combineInstructions("existing", "", "append")).toBe("existing"));
});
describe("existing core helpers in managed teacher previews", () => {
  it("generation scopes both raw drafts and retries", () => {
    const a = conversationScope(workspace("run-a"), "teacher"),
      b = conversationScope(workspace("run-b"), "teacher");
    expect(draftKey(a)).not.toBe(draftKey(b));
    expect(pendingKey(a)).not.toBe(pendingKey(b));
  });
  it("only the same completed ID acknowledges; newer raw typing survives", () => {
    const s = conversationScope(workspace("run-a"), "teacher"),
      store = storage(),
      value = {
        scope: s,
        turn: { request_id: "req-1", message: "sent", preview_id: "run-a" },
        clear_draft: true,
      };
    storePending(value, store);
    writeDraft(s, "newer edits", store);
    expect(acknowledgePending(s, "different", store)).toBeNull();
    expect(readPending(s, store)?.turn.request_id).toBe("req-1");
    expect(acknowledgePending(s, "req-1", store)).toEqual(value);
    expect(readDraft(s, store)).toBe("newer edits");
  });
  it("retry does not cross preview generation", () =>
    expect(
      sameTurn(
        { message: "same", request_id: "one", preview_id: "run-a" },
        { message: "same", preview_id: "run-b" },
      ),
    ).toBe(false));
  it("IME and Shift+Enter remain native", () => {
    expect(composerEnterAction({ key: "Enter", isComposing: true })).toBe(
      "native",
    );
    expect(composerEnterAction({ key: "Enter", shiftKey: true })).toBe(
      "native",
    );
    expect(composerEnterAction({ key: "Enter" })).toBe("send");
  });
});
