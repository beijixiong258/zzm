import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import Profile from "../src/Profile";
import { fixtureWorkspace } from "./fixtures";
import { isLocked, canReveal, canSubmit } from "../src/study";
import {
  draftKey,
  readDraft,
  writeDraft,
  clearDraft,
  type DraftScope,
} from "../src/drafts";
import { readRoute, routeHash, canAccessRoute } from "../src/routes";
import {
  effectiveAvailability,
  schedulePayload,
  moveItem,
  renumber,
  authoringErrors,
  safeExternal,
  withVersion,
  retentionText,
} from "../src/stage2";
import { SourceEditor, newQuestion } from "../src/Authoring";
import { readablePath, ReadableValue } from "../src/Versions";

import type { Question } from "../src/types";
afterEach(() => vi.unstubAllGlobals());
const mock = () => {
  const f = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(
        new Response("{}", { headers: { "Content-Type": "application/json" } }),
      ),
    );
  vi.stubGlobal("fetch", f);
  return f;
};
const scope: DraftScope = {
  user: "synthetic-user",
  session: "synthetic-session",
  version: "v1",
  question: "q1",
  intent: "answer",
};
const storage = () => {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => {
      m.set(k, v);
    },
    removeItem: (k: string) => {
      m.delete(k);
    },
  };
};
const q: Question = {
  id: "q1",
  group_id: "g1",
  ordinal: 1,
  type: "open_response",
  prompt: "Synthetic question",
  options: [],
  answer_slots: 1,
  images: [],
  source_label: "Original page 3",
  source_material_ids: [],
  source_links: [],
};
describe("stage 2 contract: explicit synthetic HTTP fixtures, not model evidence", () => {
  it("pins every learning read/write/review/export to the loaded edition", async () => {
    const f = mock();
    await api.workspace("s", "v /1");
    await api.reading("s", "custom-reading", "v /1");
    await api.answer("s", "q", "answer", "v /1");
    await api.chat("s", "ask", "q", "ask", "r", false, "v /1");
    await api.reference("s", "q", "v /1");
    await api.readReference("s", "q", "v /1");
    await api.submit("s", "v /1");
    await api.students("s", "v /1");
    await api.studentWorkspace("s", "u", "v /1");
    await api.review("s", "u", "confirmed", "review", "v /1");
    for (const [url] of f.mock.calls)
      expect(url).toContain("?version_id=v%20%2F1");
    expect(f.mock.calls[5][1].method).toBeUndefined();
    expect(api.exportUrl("s", "u", "v /1")).toContain("?version_id=v%20%2F1");
  });
  it("sends safe profile-only fields and preserves admin settings paths", async () => {
    const f = mock();
    await api.profile("Synthetic Name");
    await api.teachers();
    await api.promoteTeacher("teacher /1");
    await api.settings();
    expect(f.mock.calls[0][0]).toBe("/api/auth/profile");
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({
      name: "Synthetic Name",
    });
    expect(f.mock.calls[2][0]).toBe(
      "/api/admin/teachers/teacher%20%2F1/promote",
    );
    expect(f.mock.calls[3][0]).toBe("/api/teacher/settings");
  });
  it("separates course-level roster and global archive batches", async () => {
    const f = mock();
    await api.roster("course 1", true);
    await api.rosterAction("archive", ["u1", "u2"], "course 1");
    await api.roster(undefined, false);
    await api.rosterAction("restore", ["u1"]);
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      "/api/teacher/courses/course%201/students?archived=true",
      "/api/teacher/courses/course%201/students/archive",
      "/api/admin/students?archived=false",
      "/api/admin/students/restore",
    ]);
    expect(JSON.parse(f.mock.calls[1][1].body)).toEqual({
      user_ids: ["u1", "u2"],
    });
  });
  it("imports CSV/XLSX via multipart staging, commits with empty body", async () => {
    const f = mock();
    await api.rosterPreview(
      "c",
      new File(["name,email"], "synthetic.csv"),
      "Synthetic123",
    );
    await api.rosterCommit("c", "import /1");
    const body = f.mock.calls[0][1].body as FormData;
    expect(body.get("default_temporary_password")).toBe("Synthetic123");
    expect(f.mock.calls[0][1].headers.has("Content-Type")).toBe(false);
    expect(f.mock.calls[1][0]).toBe(
      "/api/teacher/courses/c/students/import/import%20%2F1/commit",
    );
    expect(JSON.parse(f.mock.calls[1][1].body)).toEqual({});
  });
  it("worksheet commit contains reviewed structured content, not automatic publication", async () => {
    const f = mock();
    await api.worksheetPreview(
      "s",
      new File(["Synthetic"], "synthetic.txt"),
      false,
    );
    await api.worksheetCommit(
      "s",
      "i",
      {
        title: "Review",
        groups: [{ id: "g1", title: "Core", kind: "core" }],
        questions: [q],
        reference_answers: { q1: "Synthetic reference" },
      },
      "replace",
    );
    expect(f.mock.calls[0][1].body.get("use_ai")).toBe("false");
    expect(JSON.parse(f.mock.calls[1][1].body)).toEqual({
      groups: [{ id: "g1", title: "Core", kind: "core" }],
      questions: [q],
      reference_answers: { q1: "Synthetic reference" },
      mode: "replace",
    });
  });
  it("source fields and arbitrary groups survive PATCH without losing provenance", async () => {
    const f = mock();
    await api.updateSession("s", {
      groups: [{ id: "custom-reading", title: "Reading", kind: "reading" }],
      questions: [
        {
          ...q,
          source_material_ids: ["m1", "m2"],
          source_links: ["10.1234/example"],
        },
      ],
    });
    const body = JSON.parse(f.mock.calls[0][1].body);
    expect(body.groups[0].id).toBe("custom-reading");
    expect(body.questions[0].source_label).toBe("Original page 3");
    expect(body.questions[0].source_material_ids).toEqual(["m1", "m2"]);
    expect(body.questions[0].source_links).toEqual(["10.1234/example"]);
  });
  it("uses contract material/link/version/history routes", async () => {
    const f = mock();
    await api.createLink("s", {
      url: "10.1234/example",
      visibility: "teacher",
    });
    await api.updateMaterial("s", "m", {
      title: "Changed",
      url: "https://example.invalid",
    });
    await api.archiveMaterial("s", "m");
    await api.versions("c");
    await api.publishVersion("c", "Edition");
    await api.version("c", "v1");
    await api.versionDiff("c", "v1");
    await api.restoreVersion("c", "v1", "Restored");
    await api.history();
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      "/api/sessions/s/materials/link",
      "/api/sessions/s/materials/m",
      "/api/sessions/s/materials/m",
      "/api/teacher/courses/c/versions",
      "/api/teacher/courses/c/versions/publish",
      "/api/teacher/courses/c/versions/v1",
      "/api/teacher/courses/c/versions/v1/diff",
      "/api/teacher/courses/c/versions/v1/restore",
      "/api/history",
    ]);
    expect(api.previewUrl("m /1", "v1")).toBe(
      "/api/materials/m%20%2F1/preview?version_id=v1",
    );
  });
});
describe("durable local drafts", () => {
  it("survives remount/reload and isolates all six scope dimensions", () => {
    const s = storage();
    writeDraft(scope, "Unsent synthetic", s);
    expect(readDraft({ ...scope }, s)).toBe("Unsent synthetic");
    for (const p of [
      { user: "other" },
      { session: "other" },
      { version: "v2" },
      { question: "q2" },
      { intent: "ask" as const },
      { preview: true },
    ])
      expect(readDraft({ ...scope, ...p }, s)).toBeNull();
  });
  it("clears only the successfully saved scope, never another intent or version", () => {
    const s = storage();
    const other = { ...scope, intent: "saved-answer" as const };
    writeDraft(scope, "Chat", s);
    writeDraft(other, "Answer", s);
    clearDraft(scope, s);
    expect(readDraft(other, s)).toBe("Answer");
    expect(readDraft(scope, s)).toBeNull();
  });
  it("supports clearing an intentionally emptied draft and surfaces storage failures", () => {
    const s = storage();
    writeDraft(scope, "A", s);
    writeDraft(scope, "", s);
    expect(readDraft(scope, s)).toBeNull();
    expect(
      writeDraft(scope, "A", {
        setItem: () => {
          throw new Error("full");
        },
        removeItem: () => {},
      }),
    ).toBe(false);
  });
  it("cannot collide via delimiter injection", () =>
    expect(draftKey({ ...scope, user: "a:b", session: "c" })).not.toBe(
      draftKey({ ...scope, user: "a", session: "b:c" }),
    ));
});
describe("role routes, availability and editing state", () => {
  it("allows personal settings while restricting global accounts and staff routes", () => {
    expect(canAccessRoute("teacher", "settings")).toBe(true);
    expect(canAccessRoute("student", "settings")).toBe(true);
    for (const page of ["accounts"] as const) {
      expect(canAccessRoute("admin", page)).toBe(true);
      expect(canAccessRoute("teacher", page)).toBe(true); // Course Students only, not global administration.
      expect(canAccessRoute("student", page)).toBe(false);
    }
    expect(canAccessRoute("admin", "record")).toBe(true);
    expect(canAccessRoute("student", "record")).toBe(false);
    expect(canAccessRoute("student", "profile")).toBe(true);
  });
  it("roundtrips historical routes and literal identifiers", () => {
    const r = {
      page: "record" as const,
      sid: "s /1",
      uid: "u 2",
      version: "v&1",
    };
    expect(readRoute(`#${routeHash(r)}`)).toEqual(r);
    expect(readRoute("#/workspace/%zz")).toEqual({ page: "home" });
  });
  it("time range overrides the manual flag, includes start but excludes end", () => {
    const s = {
      active: false,
      starts_at: "2026-10-01T00:00:00Z",
      ends_at: "2026-10-01T01:00:00Z",
    };
    expect(effectiveAvailability(s, Date.parse(s.starts_at)).active).toBe(true);
    expect(effectiveAvailability(s, Date.parse(s.ends_at)).reason).toBe(
      "ended",
    );
    expect(effectiveAvailability(s, Date.parse(s.starts_at) - 1).reason).toBe(
      "not_started",
    );
    expect(effectiveAvailability({ active: false }).active).toBe(false);
    expect(
      effectiveAvailability(
        { active: false, ends_at: s.ends_at },
        Date.parse(s.starts_at),
      ).active,
    ).toBe(true);
  });
  it("converts local dates to timezone-aware ISO and rejects inverted ranges", () => {
    const p = schedulePayload(true, "2026-10-01T10:00", "2026-10-01T11:00");
    expect(p.starts_at).toMatch(/Z$/);
    expect(Date.parse(p.ends_at!) - Date.parse(p.starts_at!)).toBe(3600000);
    expect(() =>
      schedulePayload(true, "2026-10-01T12:00", "2026-10-01T11:00"),
    ).toThrow();
    expect(schedulePayload(false, "", "")).toEqual({
      active: false,
      starts_at: null,
      ends_at: null,
    });
  });
  it("reorders arrays with immutable IDs and validates memberships", () => {
    const out = renumber(moveItem([q, { ...q, id: "q2" }], 0, 1));
    expect(out.map((q) => q.id)).toEqual(["q2", "q1"]);
    expect(out.map((q) => q.ordinal)).toEqual([1, 2]);
    expect(q.ordinal).toBe(1);
    expect(
      authoringErrors([{ id: "g1", title: "Core", kind: "core" }], [q]),
    ).toEqual([]);
    expect(authoringErrors([], [q])).not.toEqual([]);
    expect(newQuestion("g1", 1).source_links).toEqual([]);
  });
  it("does not expose unsafe link protocols, preserves version contexts", () => {
    expect(safeExternal("javascript:alert(1)")).toBeNull();
    expect(safeExternal("https://example.invalid/path")).toContain(
      "example.invalid",
    );
    expect(withVersion("/api/materials/m/download?x=1", "v 1")).toBe(
      "/api/materials/m/download?x=1&version_id=v+1",
    );
  });
  it("renders all-material semantics and original provenance separately", () => {
    const html = renderToStaticMarkup(
      <SourceEditor question={q} materials={[]} onChange={() => {}} />,
    );
    expect(html).toContain("All materials");
    expect(html).toContain("no selection means all eligible");
    expect(html).not.toContain("Original page 3");
  });
  it("renders English readable diffs, not JSON-only comparison", () => {
    const html = renderToStaticMarkup(
      <ReadableValue
        value={{ title: "Synthetic", questions: [{ prompt: "Question" }] }}
      />,
    );
    expect(html).toContain("Title");
    expect(html).toContain("Prompt");
    expect(html).not.toMatch(/[\u4e00-\u9fff]/);
    expect(html).not.toContain("&quot;title&quot;");
    expect(readablePath("sessions/s1/questions/q1/prompt")).toBe(
      "Sessions › s1 › Questions › q1 › Prompt",
    );
    expect(readablePath("sessions[s1]/_materials[m1]/metadata")).toBe(
      "Sessions[s1] › Materials[m1] › Content",
    );
    expect(readablePath("sessions/order")).toBe("Sessions › Order");
  });
  it("keeps authored text and teaching-language values unchanged under English diff labels", () => {
    const html = renderToStaticMarkup(
      <ReadableValue
        value={{
          title: "课程说明",
          teaching_language: "zh",
          instructions: "教师原创指令",
        }}
      />,
    );
    expect(html).toContain("Title");
    expect(html).toContain("Teaching language");
    expect(html).toContain("课程说明");
    expect(html).toContain(">zh<");
    expect(html).toContain("教师原创指令");
  });
  it("calculates archive retention without treating inactive sessions as deletion", () => {
    expect(
      retentionText("2026-10-31T00:00:00Z", Date.parse("2026-10-01T00:00:00Z")),
    ).toMatch(/^30d/);
    expect(
      retentionText("2026-10-01T00:00:00Z", Date.parse("2026-10-02T00:00:00Z")),
    ).toMatch(/^0d/);
  });
});
describe("readonly and profile role semantics", () => {
  it("disables new inactive/historical writes but allows previously revealed reference reads", () => {
    const w = fixtureWorkspace();
    w.progress.answered = w.progress.total;
    w.session.active = false;
    w.attempts.core = {
      question_id: "core",
      answer: "Synthetic saved attempt",
      revision_count: 1,
      updated_at: "2026-10-01T00:00:00Z",
      reference_revealed: false,
    };
    expect(isLocked(w)).toBe(true);
    expect(canSubmit(w)).toBe(false);
    expect(canReveal(w, "core")).toBe(false);
    w.attempts.core.reference_revealed = true;
    expect(canReveal(w, "core")).toBe(true);
    w.session.active = true;
    w.version = { id: "v1", number: 1, is_current: false, is_draft: false };
    expect(isLocked(w)).toBe(true);
  });
  it("does not lock an administrator’s own teacher draft just because classroom is inactive", () => {
    const w = fixtureWorkspace();
    w.user.role = "admin";
    w.session.active = false;
    w.version = { id: null, number: null, is_current: false, is_draft: true };
    expect(isLocked(w)).toBe(false);
    w.read_only = true;
    expect(isLocked(w)).toBe(true);
  });
  it("uses is_demo, not email/ID guesses, for password controls", () => {
    const user = {
      id: "demo-looking-real-user",
      name: "Synthetic Real QA",
      email: "qa@example.invalid",
      role: "student" as const,
      is_demo: false,
    };
    const real = renderToStaticMarkup(
      <Profile user={user} onUpdate={() => {}} />,
    );
    expect(real).toContain('autoComplete="current-password"');
    const demo = renderToStaticMarkup(
      <Profile user={{ ...user, is_demo: true }} onUpdate={() => {}} />,
    );
    expect(demo).not.toContain('autoComplete="current-password"');
    expect(demo).toContain("Synthetic demo accounts cannot change passwords");
    expect(demo).toContain("Full name");
  });
});
