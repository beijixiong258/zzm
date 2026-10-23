// Explicit synthetic frontend HTTP fixture; parent owns actual backend acceptance.
import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const artifacts = path.join(root, "artifacts", "stage3-teacher");
const clone = (value) => structuredClone(value);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let session = {
  id: "synthetic-session",
  course_id: "synthetic-course",
  number: 3,
  title: "Design a guided conversation",
  subtitle: "Synthetic teacher session — frontend fixture",
  status: "published",
  question_count: 1,
  estimated_minutes: 20,
  learning_objectives: ["Explain why a test's purpose matters."],
  instructions: "Existing private additional instructions.",
  reference_policy: "after_attempt",
  teaching_language: "en",
  teaching_profile: {
    schema_version: 1,
    background: "",
    student_profile: "",
    response_strategies: "",
    tone: "Supportive, specific and respectful; avoid excessive praise.",
    response_detail: "balanced",
    phases: ["warmup", "worksheet", "quiz", "wrap_up"],
    reading_focus: "",
    reading_question_count: 3,
    reference_delivery: "after_sufficient_answer",
    idle_hint_seconds: 0,
    presentation: "full",
  },
  active: true,
  starts_at: null,
  ends_at: null,
  effective_active: true,
  availability_reason: "manual_active",
  groups: [{ id: "g1", title: "Required assessment work", kind: "core" }],
  questions: [
    {
      id: "q1",
      group_id: "g1",
      ordinal: 1,
      type: "open_response",
      prompt: "How does test purpose affect task design?",
      options: [],
      answer_slots: 1,
      images: [],
      source_label: "Synthetic worksheet",
    },
  ],
  materials: [
    {
      id: "m1",
      title: "Synthetic teacher worksheet",
      kind: "worksheet",
      visibility: "teacher",
      source_label: "Synthetic fixture",
      status: "ready",
      excerpt: "Private fixture worksheet",
      download_url: null,
    },
  ],
  reference_answers: { q1: "PRIVATE FIXTURE REFERENCE" },
};
const initial = clone(session);
let previewMode = "normal",
  saveMode = "normal",
  nextReadMismatch = false;
const calls = [],
  checks = [],
  consoleErrors = [],
  expectedResourceErrors = [];
let server, browser;
const result = {
  evidence:
    "Explicit synthetic frontend HTTP fixtures only — not backend, SQLite or model verification",
  checks,
  consoleErrors,
  expectedResourceErrors,
  screenshots: [],
};
try {
  await fs.mkdir(artifacts, { recursive: true });
  server = await createServer({
    configFile: false,
    root,
    plugins: [react()],
    server: { host: "127.0.0.1", port: 0, strictPort: false },
  });
  await server.listen();
  const port = server.httpServer.address().port;
  const origin = `http://127.0.0.1:${port}`;
  if (!(await fetch(`${origin}/artifacts/stage3-teacher/harness.html`)).ok)
    throw new Error("Owned fixture server failed readiness check");
  if (process.env.TMPDIR) {
    process.env.TEMP = process.env.TMPDIR;
    process.env.TMP = process.env.TMPDIR;
  }
  browser = await chromium.launch({
    headless: true,
    executablePath:
      process.env.STAGE3_TEACHER_BROWSER ||
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (/Failed to load resource:.*503/.test(message.text()))
      expectedResourceErrors.push(message.text());
    else consoleErrors.push(message.text());
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      method = req.method();
    const body = method === "GET" ? null : req.postDataJSON();
    calls.push({ path: url.pathname, method, body });
    const respond = (value, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (url.pathname === "/api/sessions/synthetic-session/teaching-preview") {
      if (previewMode === "failure")
        return respond({ detail: "Explicit fixture compilation failure" }, 503);
      if (previewMode === "delayed") await sleep(450);
      return respond({
        text: `EXPLICIT FIXTURE COMPILED TEXT\n${body.teaching_profile.background}\n${body.instructions}\nEligibility: ${body.reference_policy}`,
        sections: [
          {
            id: "fixture-context",
            title: "Explicit fixture: teaching context",
            text:
              body.teaching_profile.background || "No additional background.",
          },
          {
            id: "fixture-strategy",
            title: "Explicit fixture: response strategy",
            text:
              body.teaching_profile.response_strategies ||
              "Fixture progressive guidance.",
          },
        ],
        warnings: [
          "Explicit frontend fixture preview; not generated by the real backend.",
        ],
      });
    }
    if (
      url.pathname === "/api/sessions/synthetic-session" &&
      method === "PATCH"
    ) {
      if (saveMode === "failure")
        return respond({ detail: "Explicit fixture save failure" }, 503);
      if (saveMode === "delayed") await sleep(350);
      session = { ...session, ...clone(body) };
      if (saveMode === "mismatch") nextReadMismatch = true;
      return respond(session);
    }
    if (url.pathname === "/api/sessions/synthetic-session") {
      const read = clone(session);
      if (nextReadMismatch) {
        read.teaching_profile.tone = "Explicit mismatched read-back";
        nextReadMismatch = false;
      }
      return respond(read);
    }
    if (url.pathname === "/api/teacher/sessions/synthetic-session/students")
      return respond([
        {
          user: {
            id: "synthetic-student",
            name: "Synthetic Student",
            email: "synthetic@example.invalid",
            role: "student",
          },
          answered: 1,
          total: 1,
          selected_reading: null,
          status: "submitted",
          last_active: "2026-10-06T00:00:00Z",
          submitted_at: "2026-10-06T00:00:00Z",
          version: { id: "fixture-v1", number: 1, label: "Synthetic original" },
        },
      ]);
    if (url.pathname === "/api/teacher/courses/synthetic-course/students")
      return respond([]);
    if (url.pathname === "/api/teacher/courses/synthetic-course/versions")
      return respond({
        current_version_id: "fixture-v1",
        has_unpublished_changes: true,
        versions: [
          {
            id: "fixture-v1",
            number: 1,
            label: "Synthetic original",
            created_at: "2026-10-01T00:00:00Z",
            created_by: "synthetic-teacher",
          },
        ],
      });
    return respond(
      { detail: `Unhandled explicit fixture ${method} ${url.pathname}` },
      404,
    );
  });
  await page.goto(`${origin}/artifacts/stage3-teacher/harness.html`);
  await expect(
    page.getByRole("heading", { name: "Teaching framework", exact: true }),
  ).toBeVisible();
  const label = (name) => page.getByLabel(new RegExp(`^${name}`));
  const save = () =>
    page.getByRole("button", { name: "Save content draft", exact: true });
  const compile = () =>
    page.getByRole("button", {
      name: /Compile preview|Refresh preview|Compiling/,
    });
  checks.push(
    "teacher framework integrated with configuration and existing additional instructions",
  );
  await expect(label("Additional instructions")).toHaveValue(
    initial.instructions,
  );
  await expect(label("Reference delivery")).toHaveValue(
    "after_sufficient_answer",
  );
  await label("Background & tutor role").fill(
    "Facilitate an evidence-based assessment discussion.",
  );
  await label("Student profile").fill(
    "Graduate teachers with mixed assessment experience.",
  );
  await label("Response strategies").fill(
    "Use targeted hints; adapt to each misconception and answer follow-up questions.",
  );
  await label("Response detail").selectOption("concise");
  await label("Response presentation").selectOption("paced");
  await label("Idle help invitation").fill("45");
  await label("Reference delivery").selectOption("on_request");
  await label("Reference eligibility").selectOption("after_feedback");
  await label("Reading discussion$").check();
  await label("Reading focus").fill(
    "Compare evidence for assessment validity using the assigned student readings.",
  );
  await label("Reading discussion questions").fill("4");
  await page
    .getByRole("button", {
      name: "Move Reading discussion earlier",
      exact: true,
    })
    .click();
  await expect(
    page
      .getByRole("list", { name: "Teaching phase order" })
      .locator("li strong"),
  ).toHaveText([
    "Welcome & review",
    "Required worksheet",
    "Reading discussion",
    "Optional practice quiz",
    "Wrap-up",
  ]);
  await expect(
    page.getByRole("button", { name: "Move Reading discussion earlier" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Move Optional practice quiz later" }),
  ).toBeDisabled();
  checks.push("bounded optional-phase reordering preserves required order");
  await compile().click();
  await expect(page.locator(".tf-preview-result")).toContainText(
    "Facilitate an evidence-based assessment discussion.",
  );
  const previewCall = calls.find((call) =>
    call.path.endsWith("teaching-preview"),
  );
  expect(previewCall.body.reference_policy).toBe("after_feedback");
  expect(previewCall.body.instructions).toBe(initial.instructions);
  expect(previewCall.body).not.toHaveProperty("reference_answers");
  expect(calls.filter((call) => call.method === "PATCH")).toHaveLength(0);
  checks.push(
    "unsaved compiled preview uses new API and eligibility without save/publication or private answer-key payload",
  );
  await label("Background & tutor role").fill("A newer teaching context.");
  await expect(
    page.getByText("Instructions have changed.", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".tf-preview-result")).toHaveCount(0);
  checks.push("edits invalidate and hide the older preview");
  previewMode = "delayed";
  await compile().click();
  await label("Background & tutor role").fill(
    "Latest context after a pending preview.",
  );
  await sleep(600);
  await expect(page.locator(".tf-preview-result")).toHaveCount(0);
  await expect(compile()).toBeEnabled();
  checks.push("late preview response cannot overwrite changed inputs");
  previewMode = "failure";
  await compile().click();
  await expect(
    page.getByText(/Preview unavailable: Explicit fixture compilation failure/),
  ).toBeVisible();
  await expect(label("Background & tutor role")).toHaveValue(
    "Latest context after a pending preview.",
  );
  previewMode = "normal";
  await compile().click();
  await expect(page.locator(".tf-preview-result")).toContainText(
    "Latest context after a pending preview.",
  );
  checks.push("preview errors remain visible, keep edits and allow retry");
  await label("Idle help invitation").fill("9");
  await expect(
    page.getByText(
      "Idle invitation must be disabled (0) or set to 10–300 seconds.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(compile()).toBeDisabled();
  await save().click();
  await expect(page.locator(".error-banner")).toContainText("10–300 seconds");
  await label("Idle help invitation").fill("45");
  checks.push("invalid idle values are blocked before save and preview");
  saveMode = "mismatch";
  await save().click();
  await expect(
    page.getByText(/Teaching changes could not be verified after saving/),
  ).toBeVisible();
  await expect(save()).toBeEnabled();
  await expect(label("Background & tutor role")).toHaveValue(
    "Latest context after a pending preview.",
  );
  checks.push(
    "save read-back mismatch retains edits and cannot report success",
  );
  saveMode = "delayed";
  await save().click();
  await expect(label("Background & tutor role")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Discard edits", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText(
      "Saved content draft. Students keep their published edition until the course is published.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByTestId("fixture-event")).toHaveText(
    "Saved callback after read-back",
  );
  await expect(save()).toBeDisabled();
  const patchIndex = calls.map((call) => call.method).lastIndexOf("PATCH");
  expect(calls[patchIndex + 1].method).toBe("GET");
  expect(session.teaching_profile.phases).toEqual([
    "warmup",
    "worksheet",
    "reading",
    "quiz",
    "wrap_up",
  ]);
  expect(session.teaching_profile.reading_question_count).toBe(4);
  expect(session.reference_answers).toEqual(initial.reference_answers);
  expect(session.questions).toEqual(initial.questions);
  checks.push(
    "profile and existing teacher content persist via PATCH plus GET; saving disables edits and does not publish",
  );
  await page.reload();
  await expect(label("Background & tutor role")).toHaveValue(
    "Latest context after a pending preview.",
  );
  await expect(label("Reference eligibility")).toHaveValue("after_feedback");
  await expect(label("Reading discussion questions")).toHaveValue("4");
  checks.push("reload restores saved framework and eligibility");
  await page
    .getByRole("button", { name: "Draft learning preview", exact: true })
    .click();
  await expect(page.getByTestId("fixture-event")).toHaveText(
    "Draft learning preview opened",
  );
  await page.getByRole("button", { name: "Materials", exact: true }).click();
  await expect(
    page.getByText("Synthetic teacher worksheet", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Questions & references", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Import a worksheet", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Learning records", exact: true })
    .click();
  await expect(
    page.getByText("Synthetic Student", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "View record", exact: true }).click();
  await expect(page.getByTestId("fixture-event")).toHaveText(
    "Record synthetic-student / fixture-v1",
  );
  await page
    .getByRole("button", { name: "Course roster", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Course roster/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Versions", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Course versions", exact: true }),
  ).toBeVisible();
  checks.push(
    "existing materials, worksheet/import, records, roster, versions and learning preview remain reachable",
  );
  await page
    .getByRole("button", { name: "Configuration", exact: true })
    .click();
  await compile().click();
  await expect(page.locator(".tf-preview-result")).toBeVisible();
  await page.screenshot({
    path: path.join(artifacts, "teacher-desktop.png"),
    fullPage: true,
  });
  result.screenshots.push("teacher-desktop.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("heading", { name: "Teaching framework", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(artifacts, "teacher-mobile.png"),
    fullPage: true,
  });
  result.screenshots.push("teacher-mobile.png");
  const widths = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport + 1);
  for (const name of [
    "Background & tutor role",
    "Reference delivery",
    "Additional instructions",
  ]) {
    const box = await label(name).boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(391);
  }
  await page
    .getByRole("button", { name: "Refresh preview", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(artifacts, "teacher-mobile-preview.png"),
  });
  result.screenshots.push("teacher-mobile-preview.png");
  expect(await page.locator("body").innerText()).not.toMatch(/[\u3400-\u9fff]/);
  checks.push(
    "390px responsive controls and preview fit viewport; English-only UI",
  );
  // Legacy fallback is intentionally independent of the new-session default.
  delete session.teaching_profile;
  await page.reload();
  await expect(label("Reference delivery")).toHaveValue("on_request");
  await expect(
    page.getByText(
      "This existing session keeps reference delivery on request.",
      { exact: false },
    ),
  ).toBeVisible();
  checks.push("missing legacy profile remains on-request in the rendered UI");
  expect(calls.some((call) => /publish|restore/.test(call.path))).toBe(false);
  expect(consoleErrors).toEqual([]);
  checks.push(
    "no implicit publish/restore API calls and no unexpected browser console/page errors",
  );
  result.passed = true;
} catch (error) {
  result.passed = false;
  result.error = error.stack || String(error);
  throw error;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
  result.check_count = checks.length;
  result.requests = calls.map(({ path, method }) => ({ path, method }));
  result.owned_processes_stopped = true;
  await fs.writeFile(
    path.join(artifacts, "browser-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
}
