// Isolated, labelled UI fixture for process facts, source navigation and preview reset.
import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, ".."),
  out = path.join(root, "artifacts/stage6-records");
const stamp = "2026-10-07T13:00:00Z";
const question = (id, n) => ({
  id,
  group_id: "core",
  ordinal: n,
  type: "open_response",
  prompt: `Explain synthetic assessment concept ${n}.`,
  options: [],
  images: [],
  answer_slots: 1,
  source_label: "Synthetic fixture",
});
const initial = {
  session: {
    id: "synthetic-session",
    course_id: "synthetic-course",
    number: 1,
    title: "Trace the learning process",
    subtitle: "Synthetic observations only",
    status: "published",
    question_count: 2,
    estimated_minutes: 20,
    learning_objectives: ["Explain an assessment concept."],
    instructions: "",
    reference_policy: "after_attempt",
    teaching_language: "en",
    groups: [{ id: "core", title: "Core work", kind: "core" }],
    questions: [question("q1", 1), question("q2", 2)],
    materials: [],
    reference_answers: { q1: "Synthetic instructor example" },
  },
  user: {
    id: "student-one",
    name: "Synthetic learner",
    email: "synthetic@example.invalid",
    role: "student",
  },
  selected_reading: null,
  attempts: {
    q1: {
      question_id: "q1",
      answer: "Final synthetic reasoning",
      updated_at: stamp,
      reference_revealed: false,
      revision_count: 2,
      revisions: [
        { answer: "First synthetic idea", created_at: stamp },
        { answer: "Second synthetic idea", created_at: stamp },
        { answer: "Final synthetic reasoning", created_at: stamp },
      ],
    },
  },
  messages: [],
  progress: {
    answered: 1,
    total: 2,
    active_question_ids: ["q1", "q2"],
    current_question_id: "q2",
  },
  submission: {
    status: "submitted",
    submitted_at: stamp,
    reviewed_at: null,
    teacher_note: "",
  },
  ai: {
    mode: "demo",
    configured: true,
    base_url: "",
    model: "Explicit fixture",
    web_search: { enabled: false, configured: false, provider: "tavily" },
  },
  version: { id: "edition-one", number: 1, is_current: false, is_draft: false },
  available_versions: [
    { id: "edition-one", number: 1, label: "Synthetic edition" },
  ],
  read_only: true,
  read_only_reason: "historical_version",
  tutor: {
    phase: "complete",
    started_at: stamp,
    updated_at: stamp,
    elapsed_seconds: 0,
    current_question_id: null,
    completed_question_ids: ["q1"],
    question_states: {
      q1: {
        status: "discussed",
        answer_count: 3,
        hint_count: 2,
        last_outcome: "sufficient",
      },
      q2: {
        status: "not_started",
        answer_count: 0,
        hint_count: 0,
        last_outcome: "unknown",
      },
    },
    quiz: { status: "skipped", answered: 0, total: 0, correct: null },
    reading: { answered: 0, total: 0 },
    presentation: "full",
    idle_hint_seconds: 0,
    pending_request_id: null,
    last_completed_request_id: "past-request",
  },
};
for (let i = 0; i < 20; i++)
  initial.messages.push({
    id: `message-${i}`,
    role: i % 2 ? "assistant" : "user",
    content:
      i === 18
        ? "Final synthetic reasoning"
        : `Original synthetic message ${i}. ${"This preserves a recorded observation, not an inferred score. ".repeat(5)}`,
    question_id: "q1",
    created_at: stamp,
    mode: "demo",
    intent: i % 2 ? "ask" : "answer",
  });
const learner = structuredClone(initial),
  originalLearner = JSON.stringify(learner);
let preview = structuredClone(initial);
preview.user = {
  id: "teacher-one",
  name: "Synthetic teacher",
  email: "teacher@example.invalid",
  role: "teacher",
};
preview.version = { id: null, number: null, is_current: false, is_draft: true };
preview.read_only_reason = "preview_stale";
preview.preview = {
  id: "old-test",
  revision: "old-revision",
  current_revision: "new-revision",
  stale: true,
  reset_required: true,
  pending: false,
  bound_at: stamp,
};
const calls = [],
  checks = [],
  errors = [];
let server, browser, page;
const check = (name) => checks.push({ name, passed: true });
try {
  await fs.mkdir(out, { recursive: true });
  server = await createServer({
    configFile: false,
    root,
    cacheDir: path.join(out, "vite-cache"),
    plugins: [react()],
    server: { host: "127.0.0.1", port: 0, watch: null },
  });
  await server.listen();
  const port = server.httpServer.address().port,
    base = `http://127.0.0.1:${port}`;
  if (!(await fetch(base + "/artifacts/stage6-records/harness.html")).ok)
    throw Error("Fixture server not ready");
  if (process.env.TMPDIR) {
    process.env.TEMP = process.env.TMPDIR;
    process.env.TMP = process.env.TMPDIR;
  }
  browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      p = new URL(request.url()).pathname,
      method = request.method(),
      body = method === "POST" ? request.postDataJSON() : null;
    calls.push({ path: p, method, body });
    const respond = (x) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(x),
      });
    if (
      p ===
      "/api/teacher/sessions/synthetic-session/students/student-one/workspace"
    )
      return respond(learner);
    if (p === "/api/sessions/synthetic-session/workspace")
      return respond(preview);
    if (p === "/api/teacher/sessions/synthetic-session/preview/reset") {
      expect(body.expected_revision).toBe("new-revision");
      preview = {
        ...preview,
        attempts: {},
        messages: [],
        progress: {
          answered: 0,
          total: 2,
          active_question_ids: ["q1", "q2"],
          current_question_id: "q1",
        },
        read_only: false,
        read_only_reason: null,
        submission: {
          status: "not_started",
          submitted_at: null,
          reviewed_at: null,
          teacher_note: "",
        },
        preview: {
          id: "new-test",
          revision: "new-revision",
          current_revision: "new-revision",
          stale: false,
          reset_required: false,
          pending: false,
          bound_at: stamp,
        },
        tutor: {
          ...preview.tutor,
          phase: "not_started",
          started_at: null,
          updated_at: null,
          current_question_id: null,
          completed_question_ids: [],
          last_completed_request_id: null,
          question_states: {
            q1: {
              status: "not_started",
              answer_count: 0,
              hint_count: 0,
              last_outcome: "unknown",
            },
            q2: {
              status: "not_started",
              answer_count: 0,
              hint_count: 0,
              last_outcome: "unknown",
            },
          },
        },
      };
      return respond(preview);
    }
    if (p === "/api/sessions/synthetic-session/tutor/start") {
      expect(body.preview_id).toBe("new-test");
      preview.tutor.phase = "warmup";
      preview.tutor.started_at = stamp;
      preview.tutor.last_completed_request_id = body.request_id;
      preview.messages = [
        {
          id: "new-opening",
          role: "assistant",
          content: "[Synthetic fixture] Welcome to the newly reset draft.",
          question_id: null,
          created_at: stamp,
          mode: "demo",
        },
      ];
      return respond(preview);
    }
    if (p === "/api/sessions/synthetic-session/tutor/turn") {
      expect(body.preview_id).toBe("new-test");
      preview.messages.push({
        id: "new-learner",
        role: "user",
        content: body.message,
        question_id: null,
        created_at: stamp,
        mode: "demo",
      });
      preview.messages.push({
        id: "new-reply",
        role: "assistant",
        content: "[Synthetic fixture] Your exact new test message is recorded.",
        question_id: null,
        created_at: stamp,
        mode: "demo",
      });
      preview.tutor.last_completed_request_id = body.request_id;
      return respond(preview);
    }
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unexpected fixture route ${p}` }),
    });
  });
  await page.addInitScript(() => {
    localStorage.setItem(
      "aicademiya.draft.v1:" +
        JSON.stringify([
          "teacher-one",
          "synthetic-session",
          null,
          "teacher-draft",
          "phase:complete",
          "conversation",
          "preview-run",
          "old-test",
        ]),
      "OLD RUN UNSENT CONTENT",
    );
  });
  await page.goto(base + "/artifacts/stage6-records/harness.html");
  await expect(
    page.getByRole("region", { name: "Recorded learning process" }),
  ).toBeVisible();
  check("teacher record opens with recorded process overview");
  await expect(
    page.getByText("Sufficient to discuss", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Submit for teacher review",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("textbox", { name: "Message your tutor", exact: true }),
  ).toHaveCount(0);
  check("facts remain separate from confirmation and record is read-only");
  await page.screenshot({
    path: path.join(out, "process-overview-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Locate latest reply", exact: true })
    .first()
    .click();
  const original = page.locator('[data-message-id="message-18"]');
  await expect(original).toBeInViewport();
  await expect(original).toHaveClass(/is-located/);
  await expect(original).toBeFocused();
  await expect(original).toContainText("Final synthetic reasoning");
  check("process link locates and focuses exact raw learner message");
  await page
    .getByRole("button", { name: "Process overview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Responses & revisions", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Browse questions", exact: true }),
  ).toHaveValue("q1");
  await page.getByText("Earlier responses", { exact: true }).click();
  await expect(
    page.getByText("First synthetic idea", { exact: true }),
  ).toBeVisible();
  check("revision link opens exact question and stored earlier responses");
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Process overview", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Recorded learning process" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.join(out, "process-overview-mobile.png"),
    fullPage: true,
  });
  check("mobile facts panel is reachable without horizontal overflow");
  await page
    .getByRole("button", { name: "Locate latest reply", exact: true })
    .first()
    .click();
  await expect(original).toBeInViewport();
  check("mobile process-to-original navigation reaches the target");
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page
    .getByRole("button", { name: "Preview fixture", exact: true })
    .click();
  await expect(
    page.getByText(
      "This conversation is not a test of the latest saved draft. Reset your own preview before continuing.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Message your tutor", exact: true }),
  ).toHaveCount(0);
  check("stale saved draft is readable but cannot send");
  await page
    .getByRole("button", { name: "Reset my preview", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Reset only your draft test?",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Keep this preview", exact: true })
    .click();
  expect(calls.filter((x) => x.path.endsWith("/preview/reset")).length).toBe(0);
  check("reset confirmation can be cancelled without writes");
  await page
    .getByRole("button", { name: "Reset my preview", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Reset my preview", exact: true })
    .click();
  await expect(page.locator('[data-message-id="message-18"]')).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Begin session", exact: true }),
  ).toBeVisible();
  expect(calls.filter((x) => x.path.endsWith("/tutor/start")).length).toBe(0);
  expect(JSON.stringify(learner)).toBe(originalLearner);
  check(
    "explicit own reset readback clears only trial and does not automatically infer",
  );
  await page
    .getByRole("button", { name: "Begin session", exact: true })
    .click();
  await expect(page.locator('[data-message-id="new-opening"]')).toBeVisible();
  const composer = page.getByRole("textbox", {
    name: "Message your tutor",
    exact: true,
  });
  await expect(composer).toHaveValue("");
  await composer.fill("New reset-run text");
  await composer.press("Enter");
  await expect(page.locator('[data-message-id="new-learner"]')).toHaveText(
    /New reset-run text/,
  );
  expect(calls.filter((x) => x.path.endsWith("/tutor/turn"))).toHaveLength(1);
  check("new preview uses fresh identity and no stale local draft");
  await page.screenshot({
    path: path.join(out, "new-preview-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Record fixture", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Recorded learning process" }),
  ).toBeVisible();
  expect(JSON.stringify(learner)).toBe(originalLearner);
  check("returning to observed student retains original record");
  expect(errors).toEqual([]);
  check("no unexpected page errors");
  await fs.writeFile(
    path.join(out, "result.json"),
    JSON.stringify(
      {
        status: "passed",
        evidence:
          "Labelled synthetic frontend HTTP fixture; not real backend or model evidence",
        checks,
        calls,
        page_errors: errors,
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      status: "passed",
      checks: checks.length,
      report: path.join(out, "result.json"),
    }),
  );
} catch (e) {
  await fs.mkdir(out, { recursive: true });
  if (page)
    await page
      .screenshot({ path: path.join(out, "failure.png"), fullPage: true })
      .catch(() => {});
  await fs.writeFile(
    path.join(out, "failure.json"),
    JSON.stringify(
      { error: String(e), checks, calls, page_errors: errors },
      null,
      2,
    ),
  );
  throw e;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
}
