import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, request } from "../src/api";
afterEach(() => vi.unstubAllGlobals());
function stub(body: unknown = {}, status = 200) {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}
describe("HTTP integration contract with explicit fetch fixtures", () => {
  it("sends same-origin cookie credentials and snake_case chat payload", async () => {
    const fetch = stub();
    await api.chat("session 2", "Why?", "q/1", "ask", "request-one");
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/sessions/session%202/chat");
    expect(options.credentials).toBe("include");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      message: "Why?",
      question_id: "q/1",
      intent: "ask",
      request_id: "request-one",
      web_search: false,
    });
    expect(options.headers.get("Content-Type")).toBe("application/json");
  });
  it("sends an explicitly enabled web-search flag", async () => {
    const fetch = stub();
    await api.chat("s", "Find evidence", "q", "ask", "search-on", true);
    expect(JSON.parse(fetch.mock.calls[0][1].body).web_search).toBe(true);
  });
  it("saves direct answers without a chat request", async () => {
    const fetch = stub();
    await api.answer("s", "q/1", "attempt");
    expect(fetch.mock.calls[0][0]).toBe("/api/sessions/s/answers/q%2F1");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      answer: "attempt",
    });
  });
  it("preserves actual reference rejection and HTTP status", async () => {
    stub({ detail: "Try the question first" }, 409);
    await expect(api.reference("s", "q")).rejects.toMatchObject({
      message: "Try the question first",
      status: 409,
    });
  });
  it("does not silently fall back to demo on model failure", async () => {
    const fetch = stub({ detail: "Model service unavailable" }, 502);
    await expect(
      api.chat("s", "Attempt", "q", "answer"),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("targets the exact teacher review record", async () => {
    const fetch = stub();
    await api.review(
      "s",
      "student 1",
      "needs_revision",
      "Please explain your example.",
    );
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/teacher/sessions/s/students/student%201/review",
    );
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      status: "needs_revision",
      note: "Please explain your example.",
    });
  });
  it("keeps an omitted API key out of the update", async () => {
    const fetch = stub();
    await api.saveSettings({
      mode: "openai",
      base_url: "http://localhost/v1",
      model: "test",
    });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).not.toHaveProperty(
      "api_key",
    );
  });
  it("uploads multipart without forcing a JSON content type", async () => {
    const fetch = stub();
    await api.upload(
      "s",
      new File(["explicit fixture"], "fixture.txt"),
      "teacher",
      "answer_key",
    );
    const opts = fetch.mock.calls[0][1];
    expect(opts.body).toBeInstanceOf(FormData);
    expect(opts.body.get("visibility")).toBe("teacher");
    expect(opts.headers.has("Content-Type")).toBe(false);
  });
  it("reports non-JSON server failures honestly", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(new Response("upstream error", { status: 503 })),
    );
    await expect(request("/health")).rejects.toMatchObject({
      message: "Request failed (503)",
      status: 503,
    });
  });
});
