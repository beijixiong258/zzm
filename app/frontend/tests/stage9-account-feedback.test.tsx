import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import Avatar, {
  avatarCrop,
  avatarFileError,
  avatarInitials,
  avatarPreview,
  verifyAvatarImage,
} from "../src/Avatar";
import Profile from "../src/Profile";
import Feedback, {
  feedbackDraftKey,
  feedbackValidation,
  feedbackSubmissionMatches,
  feedbackReplyMatches,
  parseFeedbackDraft,
} from "../src/Feedback";
import { api } from "../src/api";
import type { FeedbackCreate, FeedbackItem, User } from "../src/types";
const user: User = {
  id: "student-a",
  name: "Synthetic Person",
  email: "a@example.invalid",
  role: "student",
};
const payload: FeedbackCreate = {
  request_id: "safe-request_1",
  category: "bug",
  subject: "  Literal <script>  ",
  message: "  First\n\nSecond  ",
};
const item: FeedbackItem = {
  id: "f1",
  ...payload,
  subject: payload.subject.trim(),
  message: payload.message.trim(),
  status: "new",
  reply: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  revision: 1,
  author: { id: user.id, name: user.name, email: user.email, role: user.role },
};
afterEach(() => vi.unstubAllGlobals());
describe("Stage9 account and feedback contract — unit/SSR", () => {
  it("fallback initials handle multiword Unicode names without splitting a surrogate pair", () => {
    expect(avatarInitials(" Synthetic Person ")).toBe("SP");
    expect(avatarInitials("🧑 Reader")).toBe("🧑R");
    expect(avatarInitials("   ")).toBe("?");
  });
  it("reusable avatar uses the persisted URL and accessible alt, never an external service", () => {
    const html = renderToStaticMarkup(
      <Avatar
        user={{ ...user, avatar_url: "/api/users/student-a/avatar?v=hash" }}
        large
        className="synthetic"
      />,
    );
    expect(html).toContain('src="/api/users/student-a/avatar?v=hash"');
    expect(html).toContain('alt="Avatar for Synthetic Person"');
    expect(html).toContain("account-avatar large synthetic");
  });
  it("missing avatar renders accessible initials", () => {
    expect(renderToStaticMarkup(<Avatar user={user} />)).toContain(
      'aria-label="Avatar initials for Synthetic Person"',
    );
  });
  it.each(["image/svg+xml", "image/gif", "text/plain"])(
    "rejects prohibited local MIME %s",
    (type) => {
      expect(avatarFileError({ type, size: 100 })).toContain("static PNG");
    },
  );
  it("accepts exactly 5 MiB, rejects empty and over-limit input", () => {
    expect(avatarFileError({ type: "image/png", size: 5 * 1024 * 1024 })).toBe(
      "",
    );
    expect(
      avatarFileError({ type: "image/jpeg", size: 5 * 1024 * 1024 + 1 }),
    ).toContain("5 MiB");
    expect(avatarFileError({ type: "image/webp", size: 0 })).toContain("empty");
  });
  it("center crop is geometric, not a CSS-only illusion", () => {
    expect(avatarCrop(768, 256)).toEqual({ x: 256, y: 0, size: 256 });
    expect(avatarCrop(200, 601)).toEqual({ x: 0, y: 200.5, size: 200 });
  });
  it("preview uses EXIF-aware decode, draws an actual square256 and closes the bitmap", async () => {
    const close = vi.fn(),
      drawImage = vi.fn();
    const bitmap = { width: 768, height: 256, close };
    const decode = vi.fn(async () => bitmap);
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => ({ drawImage }),
      toDataURL: () => "data:image/png;base64,cropped",
    };
    vi.stubGlobal("createImageBitmap", decode);
    vi.stubGlobal("document", { createElement: () => canvas });
    const file = new File([new Uint8Array(32)], "synthetic.jpg", {
      type: "image/jpeg",
    });
    expect(await avatarPreview(file)).toContain("cropped");
    expect(decode).toHaveBeenCalledWith(file, {
      imageOrientation: "from-image",
    });
    expect(drawImage).toHaveBeenCalledWith(
      bitmap,
      256,
      0,
      256,
      256,
      0,
      0,
      256,
      256,
    );
    expect(canvas.width).toBe(256);
    expect(canvas.height).toBe(256);
    expect(close).toHaveBeenCalledOnce();
  });
  it("rejects >16M decoded pixels and releases bitmap", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", async () => ({
      width: 5000,
      height: 4000,
      close,
    }));
    await expect(
      avatarPreview(new File(["bytes"], "large.png", { type: "image/png" })),
    ).rejects.toThrow("16 million");
    expect(close).toHaveBeenCalledOnce();
  });
  it("undecodable fake image has a visible decode error", async () => {
    vi.stubGlobal("createImageBitmap", async () => {
      throw Error("bad");
    });
    await expect(
      avatarPreview(
        new File(["not image"], "fake.jpg", { type: "image/jpeg" }),
      ),
    ).rejects.toThrow("decoded");
  });
  it("rejects APNG animation control before preview decode", async () => {
    const b = new Uint8Array(20);
    b.set([97, 99, 84, 76], 12);
    await expect(
      avatarPreview(new File([b], "animated.png", { type: "image/png" })),
    ).rejects.toThrow("Animated");
  });
  it("persisted image readback requires decode and correct256 dimensions", async () => {
    class ImageMock {
      src = "";
      naturalWidth = 256;
      naturalHeight = 256;
      decode = async () => {};
    }
    vi.stubGlobal("Image", ImageMock);
    await expect(verifyAvatarImage("/api/normalized")).resolves.toBeUndefined();
    vi.stubGlobal(
      "Image",
      class extends ImageMock {
        naturalWidth = 128;
      },
    );
    await expect(verifyAvatarImage("/api/wrong")).rejects.toThrow("256");
    vi.stubGlobal(
      "Image",
      class extends ImageMock {
        decode = async () => {
          throw Error("missing");
        };
      },
    );
    await expect(verifyAvatarImage("/api/missing")).rejects.toThrow(
      "could not be loaded",
    );
  });
  it("account retains original name/password controls and policy while adding explicit avatar save", () => {
    const html = renderToStaticMarkup(
      <Profile user={user} onUpdate={() => {}} />,
    );
    expect(html).toContain("Display name");
    expect(html).toContain("Current password");
    expect(html).toMatch(/autocomplete="current-password"/i);
    expect(html).toMatch(/minlength="8"/i);
    expect(html).toMatch(/maxlength="512"/i);
    expect(html).toContain("Save avatar");
    expect(html).toContain("Remove avatar");
    expect(html).not.toContain("Unsaved centered avatar preview");
  });
  it("demo password protection stays based on is_demo metadata", () => {
    const html = renderToStaticMarkup(
      <Profile user={{ ...user, is_demo: true }} onUpdate={() => {}} />,
    );
    expect(html).toContain("Synthetic demo accounts cannot change passwords");
    expect(html).not.toContain("Current password");
  });
  it("draft keys are account scoped and preserve literal account identifiers", () => {
    expect(feedbackDraftKey("a/b")).toBe("aicademiya:feedback:v1:a%2Fb");
    expect(feedbackDraftKey("student-a")).not.toBe(
      feedbackDraftKey("student-b"),
    );
  });
  it("recovered draft preserves exact request/payload without truncation", () => {
    const draft = {
      category: "bug",
      subject: payload.subject,
      message: payload.message,
      attempt: payload,
      acceptedId: "f1",
    };
    expect(parseFeedbackDraft(JSON.stringify(draft))).toEqual(draft);
    expect(parseFeedbackDraft("broken").subject).toBe("");
    expect(
      parseFeedbackDraft(
        JSON.stringify({
          ...draft,
          attempt: { ...payload, request_id: "unsafe/" },
        }),
      ).attempt,
    ).toBeNull();
  });
  it("validates nonblank/bounds before trim with Unicode codepoints", () => {
    expect(feedbackValidation(" ", "text")).not.toBe("");
    expect(feedbackValidation("s".repeat(160), "m".repeat(6000))).toBe("");
    expect(feedbackValidation("s".repeat(160) + " ", "ok")).toContain("160");
    expect(feedbackValidation("🧑".repeat(160), "ok")).toBe("");
    expect(feedbackValidation("s", "m".repeat(6001))).toContain("6,000");
  });
  it("submission exact GET match includes durable request and all normalized text", () => {
    expect(feedbackSubmissionMatches(item, payload)).toBe(true);
    for (const change of [
      { request_id: "other" },
      { category: "idea" as const },
      { subject: "other" },
      { message: "First\nSecond" },
    ])
      expect(feedbackSubmissionMatches({ ...item, ...change }, payload)).toBe(
        false,
      );
  });
  it("reply verification requires exact target, status, normalized reply and revision", () => {
    const p = {
      status: "reviewed" as const,
      reply: " reply\nline ",
      expected_revision: 1,
    };
    const row = {
      ...item,
      status: p.status,
      reply: p.reply.trim(),
      revision: 2,
    };
    expect(feedbackReplyMatches(row, "f1", p, 2)).toBe(true);
    expect(feedbackReplyMatches(row, "other", p, 2)).toBe(false);
    expect(feedbackReplyMatches({ ...row, revision: 3 }, "f1", p, 2)).toBe(
      false,
    );
    expect(feedbackReplyMatches({ ...row, status: "new" }, "f1", p, 2)).toBe(
      false,
    );
  });
  it.each(["student", "teacher", "admin"] as const)(
    "role %s has own feedback; only admin sees Inbox",
    (role) => {
      const html = renderToStaticMarkup(<Feedback user={{ ...user, role }} />);
      expect(html).toContain("My feedback");
      expect(html).toContain("Send feedback");
      expect(html.includes("Administrator inbox")).toBe(role === "admin");
      expect(html).not.toContain("Developer inbox");
    },
  );
  it("SSR escapes literal input and never turns feedback into HTML", () => {
    vi.stubGlobal("localStorage", {
      getItem: () =>
        JSON.stringify({
          category: "general",
          subject: '<script>alert("x")</script>',
          message: "<img onerror=bad>",
          attempt: null,
          acceptedId: null,
        }),
    });
    const html = renderToStaticMarkup(<Feedback user={user} />);
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>alert");
    expect(html).toContain("&lt;img onerror=bad&gt;");
  });
  it("avatar requests use multipart/DELETE without client profile fields", async () => {
    const fetch = vi.fn(async () => new Response('{"user":{}}'));
    vi.stubGlobal("fetch", fetch);
    const file = new File(["synthetic"], "photo.png", { type: "image/png" });
    await api.uploadAvatar(file);
    await api.removeAvatar();
    await api.me();
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map((c) => c[0])).toEqual([
      "/api/auth/avatar",
      "/api/auth/avatar",
      "/api/auth/me",
    ]);
    expect(calls[0][1].method).toBe("POST");
    expect(calls[0][1].body).toBeInstanceOf(FormData);
    expect((calls[0][1].body as FormData).get("file")).toEqual(file);
    expect((calls[0][1].headers as Headers).has("Content-Type")).toBe(false);
    expect(calls[1][1].method).toBe("DELETE");
    expect(calls[1][1].body).toBeUndefined();
  });
  it("feedback wrappers route own/admin exact reads and PATCH revision explicitly", async () => {
    const fetch = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await api.feedbackCreate(payload);
    await api.feedbackList({
      offset: 25,
      limit: 25,
      category: "bug",
      status: "new",
    });
    await api.feedbackList({}, true);
    await api.feedbackGet("f /1", true);
    await api.feedbackByRequest("safe_1");
    await api.feedbackUpdate("f /1", {
      status: "reviewed",
      reply: "plain",
      expected_revision: 2,
    });
    const c = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(c.map((a) => a[0])).toEqual([
      "/api/feedback",
      "/api/feedback?offset=25&limit=25&category=bug&status=new",
      "/api/admin/feedback",
      "/api/admin/feedback/f%20%2F1",
      "/api/feedback/requests/safe_1",
      "/api/admin/feedback/f%20%2F1",
    ]);
    expect(JSON.parse(c[0][1].body as string)).toEqual(payload);
    expect(c[5][1].method).toBe("PATCH");
    expect(JSON.parse(c[5][1].body as string)).toEqual({
      status: "reviewed",
      reply: "plain",
      expected_revision: 2,
    });
  });
});
