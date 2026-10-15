// Labelled synthetic UI fixtures. Real backend/SQLite evidence is in separate pytest results.
import { chromium } from "playwright";
import { createServer, build } from "vite";
import react from "@vitejs/plugin-react";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const FRONTEND = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const OUT = path.join(FRONTEND, "artifacts/stage4-student");
await mkdir(OUT, { recursive: true });
const ai = {
  mode: "demo",
  configured: true,
  base_url: "",
  model: "stage4-synthetic-ui-only",
  last_error: "",
  web_search: { enabled: false, configured: false, provider: "tavily" },
};
const question = {
  id: "stage4-quiz-3",
  type: "single_choice",
  prompt:
    "Placeholder formative item 3: Which approach best supports a learner who is stuck?",
  options: [
    "Give the full answer immediately",
    "Provide a focused hint and invite a new attempt",
    "Move on to the next question",
    "Ask them to memorise the solution",
  ],
  images: [],
};
const feedback =
  "You chose option B, “It helps identify specific strengths and misconceptions.” That’s exactly right: guided feedback is most valuable when it pinpoints what’s working and where a specific misconception lies, so you can target your revision. Well done.\n\nFormative practice: correct. Guided feedback helps learners identify specific strengths and misconceptions, supporting targeted revision.";
const suffix =
  "\n\nOptional formative practice:\n" +
  question.prompt +
  "\n" +
  question.options.map((v, i) => `${i + 1}. ${v}`).join("\n");
const originalMessage = {
  id: "stage4-original",
  role: "assistant",
  content: feedback + suffix,
  question_id: null,
  created_at: "2026-10-07T04:01:00Z",
  mode: "demo",
  presented_question_id: question.id,
  metadata: { phase: "quiz", kind: "question", presented_question: question },
};
let w = {
  session: {
    id: "stage4-session",
    course_id: "stage4-course",
    number: 1,
    title: "Worksheet for Recap",
    subtitle:
      "Synthetic Stage4 student UI fixture · no live model or production data",
    status: "published",
    question_count: 0,
    estimated_minutes: 10,
    learning_objectives: [],
    instructions: "",
    reference_policy: "after_attempt",
    teaching_language: "en",
    groups: [],
    questions: [],
    materials: [],
    active: true,
    effective_active: true,
    availability_reason: "manual_active",
  },
  user: {
    id: "stage4-student",
    name: "Synthetic learner",
    email: "stage4@example.invalid",
    role: "student",
  },
  selected_reading: null,
  attempts: {},
  messages: [structuredClone(originalMessage)],
  progress: {
    answered: 0,
    total: 0,
    active_question_ids: [],
    current_question_id: null,
  },
  submission: {
    status: "in_progress",
    submitted_at: null,
    reviewed_at: null,
    teacher_note: "",
  },
  ai,
  tutor: {
    phase: "quiz",
    started_at: "2026-10-07T04:00:00Z",
    updated_at: "2026-10-07T04:02:00Z",
    elapsed_seconds: 120,
    current_question_id: question.id,
    completed_question_ids: [],
    question_states: {},
    quiz: { status: "active", answered: 2, total: 5, correct: 2 },
    reading: { answered: 0, total: 0 },
    presentation: "full",
    idle_hint_seconds: 0,
    pending_request_id: null,
    last_completed_request_id: null,
  },
  version: {
    id: "stage4-edition",
    number: 1,
    is_current: true,
    is_draft: false,
  },
  available_versions: [
    { id: "stage4-edition", number: 1, label: "Synthetic published fixture" },
  ],
  read_only: false,
};
const turnCalls = [],
  records = new Map(),
  failures = new Set(),
  checks = [],
  screenshots = [],
  pageErrors = [],
  blockedExternal = [];
let status = "failed",
  failure = null,
  browser,
  server,
  page,
  sequence = 0;
let held = null,
  heldRelease = null,
  poll = null;
const ok = (name) => {
  checks.push(name);
  console.log("PASS " + name);
};
const scope = (
  qid = question.id,
  edition = "stage4-edition",
  user = "stage4-student",
) => ({
  user,
  session: "stage4-session",
  version: edition,
  preview: false,
  question: qid,
  intent: "conversation",
});
const pendingKey = (s) =>
  `aicademiya.tutor-request.v1:${JSON.stringify([s.user, s.session, s.version, !!s.preview])}`;
const draftKey = (s) =>
  `aicademiya.draft.v1:${JSON.stringify([s.user, s.session, s.version, s.preview ? "preview" : "learning", s.question, s.intent])}`;
const add = (role, content, extra = {}) =>
  w.messages.push({
    id: `stage4-${++sequence}`,
    role,
    content,
    question_id: question.id,
    created_at: new Date().toISOString(),
    mode: "demo",
    ...extra,
  });
async function seedPending(s, id, submitted, draft) {
  await page.evaluate(
    ({ s, id, submitted, draft, pk, dk }) => {
      localStorage.setItem(
        pk,
        JSON.stringify({
          scope: s,
          turn: {
            request_id: id,
            message: submitted,
            action: "message",
            web_search: false,
          },
          clear_draft: true,
        }),
      );
      localStorage.setItem(dk, draft);
    },
    { s, id, submitted, draft, pk: pendingKey(s), dk: draftKey(s) },
  );
}
async function shot(name) {
  const file = path.join(OUT, name + ".png");
  await page.screenshot({ path: file, fullPage: true });
  screenshots.push(file);
}
async function idle(input) {
  await input.waitFor({ state: "visible" });
  await page.waitForFunction(() => !document.querySelector(".guided-thinking"));
}
try {
  // Dedicated build does not include concurrently edited teacher/material lanes.
  await build({
    configFile: false,
    root: FRONTEND,
    plugins: [react()],
    logLevel: "warn",
    build: {
      outDir: path.join(OUT, "harness-dist"),
      rollupOptions: {
        input: path.join(FRONTEND, "tests/stage4-student-harness.html"),
      },
    },
  });
  ok("dedicated student harness builds from current source");
  server = await createServer({
    configFile: false,
    root: FRONTEND,
    plugins: [react()],
    logLevel: "warn",
    server: { host: "127.0.0.1", port: 0, strictPort: true },
  });
  await server.listen();
  const base = server.resolvedUrls.local[0];
  browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    args: ["--disable-gpu"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
  });
  page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await context.route("**/*", async (route) => {
    if (new URL(route.request().url()).hostname !== "127.0.0.1") {
      blockedExternal.push(new URL(route.request().url()).hostname);
      return route.abort();
    }
    return route.continue();
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      pathname = url.pathname;
    const json = (body, code = 200) =>
      route.fulfill({
        status: code,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (pathname.endsWith("/workspace")) {
      if (poll && --poll.reads <= 0) {
        w.tutor.pending_request_id = null;
        w.tutor.last_completed_request_id = poll.id;
        poll = null;
      }
      return json(w);
    }
    if (pathname.endsWith("/tutor/turn")) {
      const data = req.postDataJSON();
      assert.equal(url.searchParams.get("version_id"), w.version.id);
      turnCalls.push(structuredClone(data));
      if (!records.has(data.request_id)) {
        add("user", data.message);
        records.set(data.request_id, { done: false });
      }
      if (data.message.includes("HOLD"))
        await new Promise((resolve) => {
          heldRelease = resolve;
          held = data.request_id;
        });
      if (
        data.message.includes("FAIL_ONCE") &&
        !failures.has(data.request_id)
      ) {
        failures.add(data.request_id);
        return json(
          { detail: "Synthetic failure for durable retry check" },
          503,
        );
      }
      if (!records.get(data.request_id).done) {
        add(
          "assistant",
          "[Synthetic UI fixture] Received your exact raw text.",
        );
        records.get(data.request_id).done = true;
      }
      w.tutor.last_completed_request_id = data.request_id;
      w.tutor.pending_request_id = null;
      return json(w);
    }
    if (pathname.endsWith("/export")) return json(w);
    return json({ detail: "Unexpected fixture endpoint " + pathname }, 404);
  });
  await page.goto(base + "tests/stage4-student-harness.html");
  const input = page.getByRole("textbox", { name: "Message your tutor" });
  await idle(input);
  const originalArticle = page.locator('[data-message-id="stage4-original"]');
  assert.equal(await originalArticle.locator(".guided-question").count(), 1);
  assert.equal(
    await originalArticle.locator(".guided-options button").count(),
    4,
  );
  const narrative = await originalArticle
    .locator(".guided-message-text")
    .innerText();
  assert.ok(narrative.includes("You chose option B"));
  assert.ok(narrative.includes("Formative practice: correct."));
  for (const text of [question.prompt, ...question.options]) {
    assert.equal((await originalArticle.innerText()).split(text).length - 1, 1);
    assert.equal(narrative.includes(text), false);
  }
  const textBox = await originalArticle
      .locator(".guided-message-text")
      .boundingBox(),
    cardBox = await originalArticle.locator(".guided-question").boundingBox();
  assert.ok(textBox.y + textBox.height <= cardBox.y + 1);
  assert.equal(w.messages[0].content, originalMessage.content);
  await shot("quiz-legacy-deduplicated-desktop");
  ok(
    "screenshot-specific legacy quiz: top feedback + one card, no repeated plaintext, raw fixture unchanged",
  );
  w.messages[0].metadata.narrative_text = feedback;
  w.messages[0].metadata.presentation_text = suffix;
  await page.reload();
  await idle(input);
  assert.equal(
    (await originalArticle.innerText()).split(question.prompt).length - 1,
    1,
  );
  assert.ok(
    (
      await originalArticle.locator(".guided-message-text").innerText()
    ).includes("Formative practice: correct."),
  );
  ok(
    "explicit new narrative/presentation metadata displays the same single card",
  );
  await page.locator(".guided-options button").nth(1).click();
  assert.equal(await input.inputValue(), "B");
  assert.equal(turnCalls.length, 0);
  ok(
    "structured option keeps full visible text but inserts canonical bare letter without sending",
  );
  await input.fill("First line");
  await input.press("Shift+Enter");
  await input.press("End");
  await input.press("S");
  assert.equal(await input.inputValue(), "First line\nS");
  assert.equal(turnCalls.length, 0);
  await page.reload();
  await idle(input);
  assert.equal(await input.inputValue(), "First line\nS");
  ok(
    "actual Shift+Enter inserts newline; multiline unsent draft survives reload",
  );
  for (const combination of [
    "Control+Enter",
    "Meta+Enter",
    "Alt+Enter",
    "Control+Shift+Enter",
    "Meta+Shift+Enter",
    "Alt+Shift+Enter",
  ]) {
    await input.press(combination);
    assert.equal(turnCalls.length, 0);
    assert.equal(await input.inputValue(), "First line\nS");
  }
  ok(
    "Ctrl/Meta/Alt and mixed modifiers neither send nor masquerade as newline shortcuts",
  );
  await input.dispatchEvent("compositionstart", { data: "中" });
  await input.press("Enter");
  assert.equal(turnCalls.length, 0);
  await input.dispatchEvent("compositionend", { data: "中文" });
  await input.dispatchEvent("keydown", {
    key: "Enter",
    code: "Enter",
    isComposing: true,
    bubbles: true,
    cancelable: true,
  });
  await input.dispatchEvent("keydown", {
    key: "Enter",
    keyCode: 229,
    bubbles: true,
    cancelable: true,
  });
  assert.equal(turnCalls.length, 0);
  ok(
    "Chrome DOM IME simulations: composition lifecycle, native isComposing and keyCode229 do not submit (not OS-IME evidence)",
  );
  await input.fill("Do not repeat");
  await input.dispatchEvent("keydown", {
    key: "Enter",
    repeat: true,
    bubbles: true,
    cancelable: true,
  });
  assert.equal(turnCalls.length, 0);
  await input.fill("   ");
  await input.press("Enter");
  await page
    .locator(".guided-composer")
    .evaluate((form) => form.requestSubmit());
  assert.equal(turnCalls.length, 0);
  assert.equal(await input.inputValue(), "   ");
  ok(
    "repeated Enter, whitespace and programmatic empty form submission are rejected",
  );
  await input.fill("  HOLD exact raw text\nsecond line  ");
  await input.press("Enter");
  await page.waitForFunction(
    () => !!document.querySelector(".guided-thinking"),
  );
  assert.equal(turnCalls.length, 1);
  assert.ok(held);
  assert.equal(await input.isDisabled(), true);
  await input.dispatchEvent("keydown", {
    key: "Enter",
    bubbles: true,
    cancelable: true,
  });
  await page
    .locator(".guided-composer")
    .evaluate((form) => form.requestSubmit());
  assert.equal(turnCalls.length, 1);
  assert.equal(
    await input.inputValue(),
    "  HOLD exact raw text\nsecond line  ",
  );
  heldRelease();
  heldRelease = null;
  await idle(input);
  await page.waitForFunction(
    () => document.querySelector(".guided-composer textarea").value === "",
  );
  assert.equal(turnCalls[0].message, "  HOLD exact raw text\nsecond line  ");
  assert.equal(w.messages.filter((m) => m.role === "user").length, 1);
  ok(
    "actual plain Enter sends once; busy guards reject racing form/keyboard sends; acknowledged raw multiline draft clears",
  );
  await input.fill("FAIL_ONCE durable original");
  await input.press("Enter");
  await page
    .getByText("Synthetic failure for durable retry check", { exact: false })
    .first()
    .waitFor();
  await idle(input);
  const failedId = turnCalls.at(-1).request_id;
  assert.equal(await input.inputValue(), "FAIL_ONCE durable original");
  await page.reload();
  await idle(input);
  await page.getByRole("button", { name: "Retry previous message" }).waitFor();
  assert.equal(await input.inputValue(), "FAIL_ONCE durable original");
  await input.fill("A newer unsent draft");
  await page.reload();
  await idle(input);
  await page.getByRole("button", { name: "Retry previous message" }).click();
  await idle(input);
  await page.waitForFunction(() => !document.querySelector(".guided-retry"));
  assert.equal(turnCalls.at(-1).request_id, failedId);
  assert.equal(turnCalls.at(-1).message, "FAIL_ONCE durable original");
  assert.equal(await input.inputValue(), "A newer unsent draft");
  assert.equal(
    w.messages.filter(
      (m) => m.role === "user" && m.content === "FAIL_ONCE durable original",
    ).length,
    1,
  );
  ok(
    "failure/reload/same-ID retry preserve raw history and newer draft, with no duplicate learner message",
  );
  await input.fill("FAIL_ONCE plain Enter retry");
  await input.press("Enter");
  await page.getByRole("button", { name: "Retry previous message" }).waitFor();
  await idle(input);
  const enterRetryId = turnCalls.at(-1).request_id;
  await input.press("Enter");
  await idle(input);
  await page.waitForFunction(() => !document.querySelector(".guided-retry"));
  assert.equal(turnCalls.at(-1).request_id, enterRetryId);
  assert.equal(
    w.messages.filter(
      (m) => m.role === "user" && m.content === "FAIL_ONCE plain Enter retry",
    ).length,
    1,
  );
  assert.equal(await input.inputValue(), "");
  ok(
    "plain Enter on the unchanged failed draft reuses its durable request ID rather than creating a new send",
  );
  const beforeLoad = turnCalls.length;
  w.tutor.last_completed_request_id = "stage4-completed-on-load";
  await seedPending(
    scope(),
    "stage4-completed-on-load",
    "Delivered before disconnect",
    "Delivered before disconnect",
  );
  await page.reload();
  await idle(input);
  await page.waitForFunction(
    () => document.querySelector(".guided-composer textarea").value === "",
  );
  assert.equal(turnCalls.length, beforeLoad);
  assert.equal(await page.locator(".guided-retry").count(), 0);
  ok(
    "workspace reload acknowledges only completed durable ID without resending and clears matching draft",
  );
  await seedPending(
    scope(),
    "stage4-poll-completed",
    "Old submitted draft",
    "Keep newer polling draft",
  );
  w.tutor.pending_request_id = "stage4-poll-completed";
  w.tutor.last_completed_request_id = null;
  poll = { id: "stage4-poll-completed", reads: 2 };
  await page.reload();
  await input.waitFor();
  assert.equal(await input.isDisabled(), true);
  await input.dispatchEvent("keydown", {
    key: "Enter",
    bubbles: true,
    cancelable: true,
  });
  await page
    .locator(".guided-composer")
    .evaluate((form) => form.requestSubmit());
  assert.equal(turnCalls.length, beforeLoad);
  await idle(input);
  assert.equal(await input.inputValue(), "Keep newer polling draft");
  assert.equal(await page.locator(".guided-retry").count(), 0);
  assert.equal(turnCalls.length, beforeLoad);
  ok(
    "server-pending guard plus polling acknowledgment preserve newer draft without sending another turn",
  );
  // Distinct question and edition slots must survive acknowledgments in the loaded scope.
  await page.evaluate(
    ({ a, b }) => {
      localStorage.setItem(a, "Other question draft");
      localStorage.setItem(b, "Other edition draft");
    },
    {
      a: draftKey(scope("other-question")),
      b: draftKey(scope(question.id, "other-edition")),
    },
  );
  await input.fill("Current scope delivered");
  await input.press("Enter");
  await idle(input);
  await page.waitForFunction(
    () => document.querySelector(".guided-composer textarea").value === "",
  );
  const saved = await page.evaluate(
    ({ a, b }) => [localStorage.getItem(a), localStorage.getItem(b)],
    {
      a: draftKey(scope("other-question")),
      b: draftKey(scope(question.id, "other-edition")),
    },
  );
  assert.deepEqual(saved, ["Other question draft", "Other edition draft"]);
  ok(
    "successful plain Enter clears only matching draft, preserving other question/edition scopes",
  );
  // Return to the single screenshot message for responsive inspection.
  w.messages = [structuredClone(originalMessage)];
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await idle(input);
  assert.equal(
    await page
      .getByText("Enter to send · Shift + Enter for a new line", {
        exact: true,
      })
      .isVisible(),
    true,
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
    true,
  );
  const lastOption = originalArticle.locator(".guided-options button").last();
  await lastOption.click({ trial: true });
  const optionBox = await lastOption.boundingBox(),
    streamBox = await page.locator(".guided-stream").boundingBox();
  assert.ok(
    optionBox.y >= streamBox.y - 1 &&
      optionBox.y + optionBox.height <= streamBox.y + streamBox.height + 1,
  );
  await shot("quiz-deduplicated-mobile");
  await page.locator(".guided-stream").evaluate((element) => {
    element.scrollTop = 0;
  });
  await shot("quiz-feedback-mobile-top");
  ok(
    "390px: single card options reachable in nested chat, shortcut help visible, no horizontal overflow",
  );
  w.read_only = true;
  w.read_only_reason = "historical_version";
  w.version.is_current = false;
  await page.reload();
  await page.locator(".guided-locked").waitFor();
  assert.equal(await page.locator(".guided-composer").count(), 0);
  assert.equal(await originalArticle.locator(".guided-question").count(), 1);
  assert.equal(turnCalls.length, beforeLoad + 1);
  ok(
    "historical read-only record keeps deduplicated card without editable/send UI",
  );
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(blockedExternal, []);
  status = "passed";
} catch (error) {
  failure = String(error.stack || error);
  console.error(failure);
  process.exitCode = 1;
  if (page) await shot("browser-failure");
} finally {
  if (heldRelease) heldRelease();
  if (browser) await browser.close();
  if (server) await server.close();
  await writeFile(
    path.join(OUT, "browser-result.json"),
    JSON.stringify(
      {
        status,
        evidence:
          "Actual installed Chrome with synthetic HTTP/DOM UI fixtures; not live model, production, or OS IME evidence",
        checks,
        checkCount: checks.length,
        screenshots,
        pageErrors,
        blockedExternal,
        turnRequests: turnCalls.length,
        rawOriginalPreserved: originalMessage.content === feedback + suffix,
        failure,
        resourcesClosed: true,
      },
      null,
      2,
    ),
  );
}
