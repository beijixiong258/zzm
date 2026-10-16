import { afterEach, describe, expect, it, vi } from "vitest";
import { clientId } from "../src/ids";
import { newGroup, newQuestion } from "../src/question-draft";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
afterEach(() => vi.unstubAllGlobals());

describe("private HTTP client identifiers", () => {
  it("uses getRandomValues without requiring crypto.randomUUID", () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => bytes.fill(255));
    vi.stubGlobal("crypto", { getRandomValues });
    expect(clientId()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
    expect(getRandomValues).toHaveBeenCalledOnce();
    expect(newGroup().id).toBe("g-ffffffff-ffff-4fff-bfff-ffffffffffff");
    expect(newQuestion("g-one", 1).id).toBe("q-ffffffff-ffff-4fff-bfff-ffffffffffff");
  });

  it("generates independent correctly formatted request IDs", () => {
    const ids = Array.from({ length: 1000 }, () => clientId());
    expect(ids.every((id) => uuid.test(id))).toBe(true);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
