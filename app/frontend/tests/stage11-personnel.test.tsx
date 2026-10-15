import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminAccounts from "../src/AdminAccounts";
import CourseStudents from "../src/CourseStudents";
import CourseStaff from "../src/CourseStaff";
import { accountApi } from "../src/account-management-api";
import {
  createdMatches,
  importFileError,
  importResultValid,
  importReadbackMatches,
  importPreviewMatches,
  passwordValid,
  staffMatches,
  unknownWrite,
} from "../src/account-management-state";
import { ApiError } from "../src/api";
import type { User } from "../src/types";
const actor: User = {
  id: "admin",
  name: "Synthetic Admin",
  email: "admin@example.invalid",
  role: "admin",
};
afterEach(() => vi.unstubAllGlobals());
describe("Stage11 personnel contract — unit/SSR, not backend auth", () => {
  it.each(["student", "teacher"] as const)(
    "%s cannot render global account controls",
    (role) => {
      const html = renderToStaticMarkup(
        <AdminAccounts user={{ ...actor, role }} />,
      );
      expect(html).not.toContain("Create account");
      expect(html).not.toContain("New student registration");
    },
  );
  it("admin preserves registration and all-role account panels", () => {
    const html = renderToStaticMarkup(<AdminAccounts user={actor} />);
    for (const text of [
      "New student registration",
      "Global User Accounts",
      "Create account",
      "Default import role",
      "Course staff assignments",
    ])
      expect(html).toContain(text);
    expect(html).toContain('value="student" selected');
  });
  it("student cannot render any course roster or course staff management", () => {
    const html = renderToStaticMarkup(
      <CourseStudents user={{ ...actor, role: "student" }} courses={[]} />,
    );
    expect(html).not.toContain("Create or enroll student");
  });
  it("teacher staff metadata is read-only without global listing/candidate role controls", () => {
    const html = renderToStaticMarkup(
      <CourseStaff user={{ ...actor, role: "teacher" }} courseId="fixture" />,
    );
    expect(html).toContain("only be changed by an administrator");
    expect(html).not.toContain("Candidate role");
    expect(html).not.toContain("Make primary manager");
  });
  it.each(["lettersOnly", "12345678", "a1short", "A1" + "x".repeat(511)])(
    "rejects invalid password policy: %s",
    (p) => expect(passwordValid(p)).toBe(false),
  );
  it("allows ASCII letter+digit at both bounds, Unicode count and no mixed-case/symbol requirement", () => {
    expect(passwordValid("a1234567")).toBe(true);
    expect(passwordValid("a1" + "x".repeat(510))).toBe(true);
    expect(passwordValid("a1" + "🧑".repeat(510))).toBe(true);
  });
  it("file constraints retain the specified CSV/XLSX limits", () => {
    expect(
      importFileError({ name: "fixture.csv", size: 2 * 1024 * 1024 }),
    ).toBe("");
    expect(
      importFileError({ name: "fixture.csv", size: 2 * 1024 * 1024 + 1 }),
    ).toContain("2 MiB");
    expect(
      importFileError({ name: "fixture.xlsx", size: 2 * 1024 * 1024 }),
    ).toBe("");
    expect(importFileError({ name: "fixture.xlsx", size: 2 * 1024 * 1024 + 1 })).toContain("2 MiB");
    expect(importFileError({ name: "fixture.zip", size: 100 })).toContain(
      "CSV",
    );
  });
  it("creation acknowledgement checks role, exact name/email and initial password requirement", () => {
    const draft = {
      name: " Fixture ",
      email: "F@example.invalid",
      role: "teacher" as const,
      temporary_password: "MemoryOnly1",
    };
    const user = {
      ...actor,
      id: "new",
      name: "Fixture",
      email: "f@example.invalid",
      role: "teacher" as const,
      must_change_password: true,
    };
    expect(createdMatches(user, draft)).toBe(true);
    expect(createdMatches({ ...user, role: "admin" }, draft)).toBe(false);
    expect(
      createdMatches({ ...user, must_change_password: false }, draft),
    ).toBe(false);
  });
  it("import result requires reviewed counts and distinct exact-ID cardinality", () => {
    const p = {
      import_id: "i",
      valid_count: 2,
      error_count: 0,
      rows: [
        {
          row_number: 2,
          name: "A",
          email: "a@example.invalid",
          role: "student" as const,
          action: "create" as const,
          errors: [],
          warnings: [],
        },
        {
          row_number: 3,
          name: "B",
          email: "b@example.invalid",
          role: "teacher" as const,
          action: "skip" as const,
          errors: [],
          warnings: [],
        },
      ],
    };
    expect(
      importResultValid({ created: 1, skipped: 1, user_ids: ["a", "b"] }, p),
    ).toBe(true);
    expect(
      importResultValid({ created: 1, skipped: 1, user_ids: ["a", "a"] }, p),
    ).toBe(false);
    expect(
      importResultValid({ created: 2, skipped: 0, user_ids: ["a", "b"] }, p),
    ).toBe(false);
  });
  it("staff readback checks course+active role+single explicit primary+owner continuity", () => {
    const d = {
      course: {
        id: "c",
        code: "S",
        title: "Fixture",
        owner_id: "admin",
        trashed_at: null,
      },
      staff: [{ user: actor, active: true, is_primary: true }],
    };
    expect(staffMatches(d, "c", { kind: "primary", uid: "admin" })).toBe(true);
    expect(staffMatches(d, "other", { kind: "primary", uid: "admin" })).toBe(
      false,
    );
    expect(
      staffMatches({ ...d, course: { ...d.course, owner_id: "other" } }, "c", {
        kind: "primary",
        uid: "admin",
      }),
    ).toBe(false);
    expect(
      staffMatches({ ...d, staff: [{ ...d.staff[0], active: false }] }, "c", {
        kind: "add",
        uid: "admin",
      }),
    ).toBe(false);
    expect(
      staffMatches({ ...d, staff: [] }, "c", { kind: "remove", uid: "admin" }),
    ).toBe(true);
  });
  it("import readback uses exact GET target IDs, created name/role/password state while preserving skip names", () => {
    const preview = {
      import_id: "i",
      valid_count: 2,
      error_count: 0,
      rows: [
        {
          row_number: 2,
          name: "New Person",
          email: "new@example.invalid",
          role: "student" as const,
          action: "create" as const,
          errors: [],
          warnings: [],
        },
        {
          row_number: 3,
          name: "Do not overwrite",
          email: "old@example.invalid",
          role: "teacher" as const,
          action: "skip" as const,
          errors: [],
          warnings: [],
        },
      ],
    };
    const result = { created: 1, skipped: 1, user_ids: ["new", "old"] };
    const base = {
      active: true,
      archived_at: null,
      purge_at: null,
      assigned_course_count: 0,
      owned_course_count: 0,
      staff_courses: [],
    };
    const accounts = [
      {
        ...base,
        user: {
          id: "new",
          name: "New Person",
          email: "new@example.invalid",
          role: "student" as const,
          must_change_password: true,
        },
      },
      {
        ...base,
        user: {
          id: "old",
          name: "Original Name",
          email: "old@example.invalid",
          role: "teacher" as const,
          must_change_password: false,
        },
      },
    ];
    expect(importReadbackMatches(accounts, result, preview)).toBe(true);
    expect(
      importReadbackMatches(
        [
          { ...accounts[0], user: { ...accounts[0].user, id: "wrong" } },
          accounts[1],
        ],
        result,
        preview,
      ),
    ).toBe(false);
    expect(
      importReadbackMatches(
        [
          { ...accounts[0], user: { ...accounts[0].user, name: "different" } },
          accounts[1],
        ],
        result,
        preview,
      ),
    ).toBe(false);
    expect(
      importPreviewMatches(preview, {
        ...preview,
        rows: preview.rows.map((r) => ({ ...r })),
      }),
    ).toBe(true);
    expect(
      importPreviewMatches(preview, {
        ...preview,
        rows: [{ ...preview.rows[0], role: "admin" }, preview.rows[1]],
      }),
    ).toBe(false);
  });
  it("only definitive 4xx is treated as known write rejection", () => {
    expect(unknownWrite(new ApiError("conflict", 409))).toBe(false);
    expect(unknownWrite(new ApiError("lost", 503))).toBe(true);
    expect(unknownWrite(new TypeError("network"))).toBe(true);
  });
  it("frozen global wrapper paths, role-only and explicit status DTOs", async () => {
    const fetch = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await accountApi.list({
      q: "test+",
      role: "teacher",
      active: false,
      offset: 50,
      limit: 50,
    });
    await accountApi.get("u /1");
    await accountApi.role("u /1", "student");
    await accountApi.status("u /1", false);
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map((c) => c[0])).toEqual([
      "/api/admin/users?q=test%2B&role=teacher&active=false&offset=50&limit=50",
      "/api/admin/users/u%20%2F1",
      "/api/admin/users/u%20%2F1",
      "/api/admin/users/u%20%2F1/status",
    ]);
    expect(JSON.parse(calls[2][1].body as string)).toEqual({ role: "student" });
    expect(JSON.parse(calls[3][1].body as string)).toEqual({ active: false });
  });
  it("review/commit/recovery transport includes default Student and no returned or stored password", async () => {
    const fetch = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    const file = new File(
      ["name,email\nSynthetic,s@example.invalid"],
      "fixture.csv",
      { type: "text/csv" },
    );
    await accountApi.preview(file, "student", "");
    await accountApi.commit("i /1");
    await accountApi.importState("i /1");
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    const form = calls[0][1].body as FormData;
    expect(form.get("default_role")).toBe("student");
    expect(form.has("default_temporary_password")).toBe(false);
    expect(calls[1][0]).toBe("/api/admin/users/import/i%20%2F1/commit");
    expect(calls[2][1].method).toBeUndefined();
  });
  it("staff mutations never spoof actor/role or transfer through remove", async () => {
    const fetch = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await accountApi.courses();
    await accountApi.staff("c/1");
    await accountApi.addStaff("c/1", "u");
    await accountApi.primary("c/1", "u");
    await accountApi.removeStaff("c/1", "u");
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map((c) => c[0])).toEqual([
      "/api/admin/courses",
      "/api/courses/c%2F1/staff",
      "/api/courses/c%2F1/staff",
      "/api/courses/c%2F1/staff/primary",
      "/api/courses/c%2F1/staff/u",
    ]);
    expect(JSON.parse(calls[2][1].body as string)).toEqual({ user_id: "u" });
    expect(calls[4][1].method).toBe("DELETE");
    expect(calls[4][1].body).toBeUndefined();
  });
});
