import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { readRoute, routeHash } from "../src/routes";
import { permittedSection, SETTINGS_SECTIONS } from "../src/stage7-settings";
import type { FeedbackCreate, User } from "../src/types";

afterEach(() => vi.unstubAllGlobals());
describe("Stage9 parent navigation and transport contract", () => {
  it.each(["student", "teacher", "admin"] as const)("Feedback belongs to personal Settings for %s", role => {
    const user: User = { id: "synthetic", name: "Synthetic", email: "synthetic@example.invalid", role };
    expect(permittedSection(user, "feedback")).toBe("feedback");
    expect(permittedSection(user, "account")).toBe("account");
    for (const section of ["model", "search", "users"] as const)
      expect(permittedSection(user, section)).toBe(role === "admin" || (role === "teacher" && section === "users") ? section : "account");
  });
  it("roundtrips Feedback without removing the existing settings sections", () => {
    expect(readRoute("#/settings/feedback")).toEqual({ page: "settings", section: "feedback" });
    expect(routeHash({ page: "settings", section: "feedback" })).toBe("/settings/feedback");
    expect(SETTINGS_SECTIONS.map(s => s.id)).toEqual(["account", "feedback", "model", "search", "users"]);
  });
  it("uses multipart authenticated self-only avatar write and explicit remove", async () => {
    const fetch = vi.fn(async () => new Response("{}", { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    const file = new File([new Uint8Array([1, 2, 3])], "synthetic.png", { type: "image/png" });
    await api.uploadAvatar(file); await api.removeAvatar(); await api.me();
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(c => c[0])).toEqual(["/api/auth/avatar", "/api/auth/avatar", "/api/auth/me"]);
    expect(calls[0][1].method).toBe("POST");
    expect(calls[0][1].body).toBeInstanceOf(FormData);
    expect((calls[0][1].body as FormData).get("file")).toBe(file);
    expect((calls[0][1].headers as Headers).has("Content-Type")).toBe(false);
    expect(calls[1][1].method).toBe("DELETE");
    expect(calls[1][1].body).toBeUndefined();
    expect(calls.every(c => c[1].credentials === "include")).toBe(true);
  });
  it("distinguishes own feedback recovery and administrator inbox/update paths", async () => {
    const fetch = vi.fn(async () => new Response("{}", { headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    const body: FeedbackCreate = { request_id: "synthetic-1", category: "idea", subject: "Synthetic idea", message: "A synthetic suggestion" };
    await api.feedbackCreate(body);
    await api.feedbackList({ offset: 25, limit: 25, category: "idea", status: "new" });
    await api.feedbackList({}, true);
    await api.feedbackGet("entry /1"); await api.feedbackGet("entry /1", true);
    await api.feedbackByRequest("synthetic-1");
    await api.feedbackUpdate("entry /1", { expected_revision: 1, status: "reviewed", reply: "Synthetic human reply" });
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(c => c[0])).toEqual([
      "/api/feedback", "/api/feedback?offset=25&limit=25&category=idea&status=new", "/api/admin/feedback",
      "/api/feedback/entry%20%2F1", "/api/admin/feedback/entry%20%2F1", "/api/feedback/requests/synthetic-1", "/api/admin/feedback/entry%20%2F1",
    ]);
    expect(JSON.parse(calls[0][1].body as string)).toEqual(body);
    expect(calls[6][1].method).toBe("PATCH");
    expect(JSON.parse(calls[6][1].body as string)).toEqual({ expected_revision: 1, status: "reviewed", reply: "Synthetic human reply" });
  });
});
