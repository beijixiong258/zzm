import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ChangePassword from "../src/ChangePassword";

import { api } from "../src/api";

afterEach(() => vi.unstubAllGlobals());
const user = {
  id: "synthetic-setup-user",
  name: "Synthetic learner",
  email: "learner@example.invalid",
  role: "student" as const,
  must_change_password: true,
};

describe("first-login password flow contract", () => {
  it("renders three masked fields and no course navigation", () => {
    const html = renderToStaticMarkup(
      <ChangePassword
        user={user}
        onComplete={() => {}}
        onLogout={async () => {}}
      />,
    );
    expect(html.match(/type="password"/g) || []).toHaveLength(3);
    expect(html).toContain("Make this account yours.");
    expect(html).toContain("learner@example.invalid");
    expect(html).not.toContain("Question navigator");
    expect(html).not.toContain("sidebar");
  });
  it("renders English password guidance and continuation", () => {
    const html = renderToStaticMarkup(
      <ChangePassword
        user={user}
        onComplete={() => {}}
        onLogout={async () => {}}
      />,
    );
    expect(html).toContain(
      "Use at least 8 characters with a letter and a digit",
    );
    expect(html).toContain("Save password and continue");
    expect(html).not.toMatch(/[\u4e00-\u9fff]/);
  });
  it("sends change-password fields only in the POST body", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ user: { ...user, must_change_password: false } }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetch);
    await api.changePassword("SYNTHETIC_OLD_ONLY", "SYNTHETIC_NEW_ONLY");
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe("/api/auth/change-password");
    expect(opts.method).toBe("POST");
    expect(opts.credentials).toBe("include");
    expect(JSON.parse(opts.body)).toEqual({
      current_password: "SYNTHETIC_OLD_ONLY",
      new_password: "SYNTHETIC_NEW_ONLY",
    });
  });
  it("provisions a student only through the teacher-owned course endpoint", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ user, course_id: "course one" }), {
          status: 200,
        }),
      );
    vi.stubGlobal("fetch", fetch);
    await api.provisionStudent("course one", {
      name: "Synthetic learner",
      email: "learner@example.invalid",
      temporary_password: "SYNTHETIC_TEMP_ONLY",
    });
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe("/api/teacher/courses/course%20one/students");
    expect(JSON.parse(opts.body)).not.toHaveProperty("role");
    expect(JSON.parse(opts.body).temporary_password).toBe(
      "SYNTHETIC_TEMP_ONLY",
    );
  });
});
