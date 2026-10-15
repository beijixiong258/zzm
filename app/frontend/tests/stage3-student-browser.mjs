// Synthetic UI fixtures only. Real backend/model acceptance is separate.
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
const ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const OUT = path.join(ROOT, "artifacts/stage3/student-fixture");
await mkdir(OUT, { recursive: true });
const server = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (pathname.endsWith("/transcript")) {
      const body =
        "<!doctype html><h1>Synthetic UI download fixture</h1><p>Not a real backend transcript test.</p>";
      res.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Disposition":
          'attachment; filename="synthetic-transcript.html"',
        "Content-Length": Buffer.byteLength(body),
      });
      res.end(body);
      return;
    }
    const file = path.resolve(
      ROOT,
      "frontend/dist",
      pathname === "/" ? "index.html" : "." + pathname,
    );
    if (!file.startsWith(path.join(ROOT, "frontend/dist"))) throw Error("path");
    const data = await readFile(file);
    res.writeHead(200, {
      "Content-Type": file.endsWith(".js")
        ? "text/javascript"
        : file.endsWith(".css")
          ? "text/css"
          : file.endsWith(".svg")
            ? "image/svg+xml"
            : file.endsWith(".png")
              ? "image/png"
              : "text/html",
    });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const ai = {
  mode: "demo",
  configured: true,
  base_url: "",
  model: "synthetic-ui-fixture",
  last_error: "",
  web_search: { enabled: true, configured: true, provider: "tavily" },
};
const student = {
  id: "ui-student",
  name: "Synthetic learner",
  email: "synthetic@example.invalid",
  role: "student",
  is_demo: true,
};
let viewer = student;
const q1 = {
  id: "q1",
  group_id: "g1",
  ordinal: 1,
  type: "open_response",
  prompt: "What does reliability mean in language assessment?",
  options: [],
  answer_slots: 1,
  images: [],
  source_label: "Synthetic UI example",
};
const q2 = {
  id: "q2",
  group_id: "g2",
  ordinal: 2,
  type: "image_matching",
  prompt: "Compare the three scatter plots. Describe their relationships.",
  options: [],
  answer_slots: 3,
  images: ["a", "b", "c"].map((x, i) => ({
    label: String.fromCharCode(65 + i),
    url: `/api/assets/s4-graph-${x}.png`,
    alt: `Scatter plot ${String.fromCharCode(65 + i)}`,
  })),
  source_label: "Existing sample figure assets used for UI rendering only",
};
const session = {
  id: "fixture-session",
  course_id: "fixture-course",
  title: "A conversation about assessment",
  subtitle: "Synthetic UI fixture · no live model",
  number: 1,
  status: "published",
  question_count: 2,
  estimated_minutes: 20,
  learning_objectives: [
    "Distinguish consistency from validity",
    "Explain your thinking with an example",
  ],
  instructions: "",
  reference_policy: "after_attempt",
  teaching_language: "en",
  groups: [
    {
      id: "g1",
      title: "Recall & apply",
      kind: "core",
      description: "Think about consistency across occasions and raters.",
    },
    {
      id: "g2",
      title: "Visual reasoning",
      kind: "core",
      description: "Use A, B and C in your response.",
    },
  ],
  questions: [q1, q2],
  materials: [
    {
      id: "m1",
      title: "Synthetic student reading",
      kind: "reading",
      visibility: "student",
      source_label: "Synthetic fixture",
      status: "ready",
      excerpt: "A short synthetic reading about assessment.",
      preview_kind: "text",
      preview_url: "/api/materials/m1/preview",
      download_url: "/api/materials/m1/download",
    },
  ],
  active: true,
  starts_at: null,
  ends_at: null,
  effective_active: true,
  availability_reason: "manual_active",
};
const tutor = {
  phase: "not_started",
  started_at: null,
  updated_at: null,
  elapsed_seconds: 0,
  current_question_id: null,
  completed_question_ids: [],
  question_states: {},
  quiz: { status: "not_offered", answered: 0, total: 0, correct: null },
  reading: { answered: 0, total: 0 },
  presentation: "full",
  idle_hint_seconds: 10,
  pending_request_id: null,
};
let w = {
  session,
  user: student,
  selected_reading: null,
  attempts: {},
  messages: [],
  progress: {
    answered: 0,
    total: 2,
    active_question_ids: ["q1", "q2"],
    current_question_id: "q1",
  },
  submission: {
    status: "not_started",
    submitted_at: null,
    reviewed_at: null,
    teacher_note: "",
  },
  ai,
  tutor,
  version: { id: "edition-1", number: 1, is_current: true, is_draft: false },
  available_versions: [
    { id: "edition-1", number: 1, label: "Published fixture" },
  ],
  read_only: false,
  read_only_reason: null,
};
let seq = 0,
  startCalls = 0,
  turnCalls = [];
const records = new Map();
const failures = new Set();
let pollCompletion = null;
const add = (role, content, qid = null, extra = {}) =>
  w.messages.push({
    id: `message-${++seq}`,
    role,
    content,
    question_id: qid,
    created_at: new Date().toISOString(),
    mode: "demo",
    ...extra,
  });
function saveAnswer(qid, answer) {
  const old = w.attempts[qid];
  w.attempts[qid] = {
    question_id: qid,
    answer,
    revision_count: (old?.revision_count || 0) + 1,
    reference_revealed: old?.reference_revealed || false,
    updated_at: new Date().toISOString(),
    revisions: [
      ...(old?.revisions || []),
      ...(old ? [{ answer: old.answer, created_at: old.updated_at }] : []),
    ],
  };
  w.progress.answered = Object.keys(w.attempts).length;
}
const checks = [],
  screenshots = [],
  pageErrors = [];
let status = "failed",
  failure = null;
const ok = (name) => {
  checks.push(name);
  console.log("PASS " + name);
};
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--disable-gpu"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
page.on("pageerror", (e) => pageErrors.push(e.message));
async function shot(name) {
  const p = path.join(OUT, name + ".png");
  await page.screenshot({ path: p, fullPage: true });
  screenshots.push(p);
}
await page.route("**/api/**", async (route) => {
  const req = route.request(),
    url = new URL(req.url()),
    p = url.pathname,
    method = req.method();
  const data = method === "POST" ? req.postDataJSON() : null;
  const json = (body, status = 200) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  if (p.startsWith("/api/assets/"))
    return route.fulfill({
      contentType: "image/png",
      body: await readFile(
        path.join(ROOT, "sample_data/assets", path.basename(p)),
      ),
    });
  if (p === "/api/bootstrap")
    return json({
      app_name: "AIcademiya",
      demo_enabled: true,
      default_locale: "en",
      ai,
    });
  if (p === "/api/auth/me") return json({ user: viewer });
  if (p === "/api/courses")
    return json([
      {
        id: "fixture-course",
        code: "QA",
        title: "Synthetic UI course",
        description: "UI fixture only",
        student_count: 1,
      },
    ]);
  if (p === "/api/courses/fixture-course/sessions") return json([session]);
  if (p === "/api/sessions/fixture-session") return json(session);
  if (p.endsWith("/workspace")) {
    if (pollCompletion && --pollCompletion.reads === 0) {
      w.tutor.last_completed_request_id = pollCompletion.id;
      w.tutor.pending_request_id = null;
      pollCompletion = null;
    }
    return json(w);
  }
  if (p.endsWith("/tutor/start")) {
    startCalls++;
    if (w.tutor.phase === "not_started") {
      w.tutor.phase = "warmup";
      w.tutor.started_at = new Date().toISOString();
      add(
        "assistant",
        "[Demo preview] Welcome. What do you remember about reliable assessment?",
      );
    }
    return json(w);
  }
  if (p.endsWith("/tutor/turn")) {
    turnCalls.push(structuredClone(data));
    if (
      w.submission.status === "submitted" ||
      !w.version.is_current ||
      !session.active
    )
      return json({ detail: "Read-only" }, 409);
    if (records.get(data.request_id)?.done) return json(w);
    if (!records.has(data.request_id)) {
      add("user", data.message, w.tutor.current_question_id, {
        intent: data.action === "hint" ? "ask" : "answer",
      });
      records.set(data.request_id, { done: false });
    }
    if (data.message.includes("FAIL_ONCE") && !failures.has(data.request_id)) {
      failures.add(data.request_id);
      w.ai.last_error = "Synthetic provider failure for retry verification.";
      return json({ detail: w.ai.last_error }, 503);
    }
    w.ai.last_error = "";
    w.submission.status = "in_progress";
    w.tutor.updated_at = new Date().toISOString();
    w.tutor.elapsed_seconds = 120;
    if (data.action === "review_question") {
      w.tutor.phase = "worksheet";
      w.tutor.current_question_id = data.question_id;
      add(
        "assistant",
        "[Demo preview] Let us revisit this question.",
        data.question_id,
        { presented_question_id: data.question_id },
      );
    } else if (w.tutor.phase === "warmup") {
      w.tutor.phase = "worksheet";
      w.tutor.current_question_id = "q1";
      add(
        "assistant",
        "[Demo preview] Thank you. Let us explore consistency through a question.",
        "q1",
        { presented_question_id: "q1" },
      );
    } else if (data.action === "hint") {
      w.tutor.question_states.q1 = {
        status: "in_progress",
        answer_count: w.attempts.q1?.revision_count || 0,
        hint_count: 1,
        last_outcome: "needs_retry",
      };
      add(
        "assistant",
        "[Demo preview] Consider whether a score changes when the rater changes.",
        "q1",
      );
    } else if (data.action === "skip_quiz") {
      w.tutor.phase = "complete";
      w.tutor.quiz.status = "skipped";
      add(
        "assistant",
        "[Demo preview] The optional quiz was skipped. Your actual conversation remains available from Download.",
      );
    } else if (w.tutor.current_question_id === "q1") {
      saveAnswer("q1", data.message);
      if (data.message.includes("FAIL_ONCE")) {
        w.tutor.question_states.q1 = {
          status: "in_progress",
          answer_count: 1,
          hint_count: 1,
          last_outcome: "needs_retry",
        };
        add(
          "assistant",
          "[Demo preview] Try distinguishing consistency from measuring the intended construct.\n\nUse an example to explain your thinking.",
          "q1",
        );
      } else {
        w.tutor.question_states.q1 = {
          status: "discussed",
          answer_count: w.attempts.q1.revision_count,
          hint_count: 1,
          last_outcome: "sufficient",
        };
        w.tutor.completed_question_ids = ["q1"];
        w.tutor.current_question_id = "q2";
        add(
          "assistant",
          "[Demo preview] Your distinction is clearer. Let us use the figures next.",
          "q1",
          { presented_question_id: "q2" },
        );
      }
    } else if (w.tutor.current_question_id === "q2") {
      saveAnswer("q2", data.message);
      w.tutor.question_states.q2 = {
        status: "discussed",
        answer_count: 1,
        hint_count: 0,
        last_outcome: "sufficient",
      };
      w.tutor.completed_question_ids = ["q1", "q2"];
      w.tutor.current_question_id = null;
      w.tutor.phase = "quiz_offer";
      w.tutor.quiz.status = "offered";
      add(
        "assistant",
        "[Demo preview] Would you like an optional practice quiz?",
        "q2",
      );
    }
    records.get(data.request_id).done = true;
    w.tutor.last_completed_request_id = data.request_id;
    return json(w);
  }
  if (p.includes("/answers/")) {
    saveAnswer(p.split("/").at(-1), data.answer);
    return json(w);
  }
  if (p.includes("/references/")) {
    const q = p.split("/").at(-1);
    if (!w.attempts[q]) return json({ detail: "Try first" }, 409);
    w.attempts[q].reference_revealed = true;
    return json({
      question_id: q,
      reference:
        "Synthetic instructor example: consistency across measurements.",
      source_label: "Synthetic fixture key",
    });
  }
  if (p.endsWith("/submit")) {
    w.submission.status = "submitted";
    w.submission.submitted_at = new Date().toISOString();
    return json(w);
  }
  if (p.endsWith("/review")) {
    w.submission.status = data.status;
    w.submission.teacher_note = data.note;
    w.submission.reviewed_at = new Date().toISOString();
    return json(w);
  }
  if (p.endsWith("/transcript")) return route.continue();
  if (p.endsWith("/export")) return json(w);
  if (p === "/api/history") return json([]);
  if (p.includes("/materials/"))
    return route.fulfill({
      contentType: "text/plain",
      body: "Synthetic reading content",
    });
  return json({ detail: "Unimplemented synthetic fixture " + p }, 404);
});
try {
  await page.goto(base + "/#/workspace/fixture-session");
  await page.getByText("[Demo preview] Welcome.", { exact: false }).waitFor();
  assert.equal(startCalls, 1);
  assert.equal(await page.locator(".guided-composer textarea").count(), 1);
  assert.equal(await page.locator(".intent-switch:visible").count(), 0);
  assert.equal(await page.getByLabel("Edit saved response").count(), 0);
  ok("single composer, proactive opening, no compulsory second answer form");
  const input = page.getByRole("textbox", { name: "Message your tutor" });
  await input.fill("A durable warm-up draft");
  await page.reload();
  await input.waitFor();
  assert.equal(await input.inputValue(), "A durable warm-up draft");
  assert.equal(startCalls, 1);
  ok("refresh retains unsent draft without duplicating opening");
  await input.fill(
    "I remember consistency across raters, but how does it relate to validity?",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByText("[Demo preview] Thank you.", { exact: false }).waitFor();
  assert.equal(turnCalls.at(-1).intent, undefined);
  ok("natural answer plus question uses guided turn API");
  const beforeIdle = turnCalls.length;
  await page.clock.install();
  await page.clock.fastForward(16000);
  await page.getByText("Need a nudge?", { exact: true }).waitFor();
  assert.equal(turnCalls.length, beforeIdle);
  ok("idle invitation performs no automatic model/search request");
  await page
    .getByRole("button", { name: "Ask for a hint", exact: true })
    .click();
  await page
    .getByText("Consider whether a score changes", { exact: false })
    .waitFor();
  assert.equal(turnCalls.at(-1).action, "hint");
  ok("hint request is deliberate and separate from saving an answer");
  // Labelled fixture: a commit becomes visible on the poll, not the first load.
  const pollId = w.tutor.last_completed_request_id;
  w.tutor.pending_request_id = pollId;
  w.tutor.last_completed_request_id = null;
  pollCompletion = { id: pollId, reads: 2 };
  const retryScope = { user: student.id, session: session.id, version: "edition-1", preview: false, question: "q1", intent: "conversation" };
  await page.evaluate(({scope,id}) => {
    const pending = `aicademiya.tutor-request.v1:${JSON.stringify([scope.user,scope.session,scope.version,false])}`;
    const draft = `aicademiya.draft.v1:${JSON.stringify([scope.user,scope.session,scope.version,"learning",scope.question,scope.intent])}`;
    localStorage.setItem(pending, JSON.stringify({scope,turn:{request_id:id,message:"Acknowledged old text"},clear_draft:true}));
    localStorage.setItem(draft,"Keep my newer unsent draft");
  }, {scope:retryScope,id:pollId});
  const beforePoll = turnCalls.length;
  await page.reload();
  await page.getByText("Your tutor is responding…", {exact:true}).waitFor();
  await page.clock.fastForward(3000);
  await page.waitForFunction(() => !document.querySelector('.guided-thinking'));
  assert.equal(await input.inputValue(), "Keep my newer unsent draft");
  assert.equal(await page.getByRole("button", {name:"Retry previous message"}).count(), 0);
  assert.equal(turnCalls.length,beforePoll);
  ok("poll acknowledges completed request by ID without resending or clearing a newer draft");
  await input.fill(
    "FAIL_ONCE I think it concerns consistency. Could you clarify?",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page
    .getByText("Synthetic provider failure for retry verification.")
    .first()
    .waitFor();
  const failedId = turnCalls.at(-1).request_id;
  assert.equal(
    w.messages.filter(
      (m) => m.role === "user" && m.content.includes("FAIL_ONCE"),
    ).length,
    1,
  );
  await page.reload();
  await page.getByRole("button", { name: "Retry previous message" }).waitFor();
  await page.getByRole("button", { name: "Retry previous message" }).click();
  await page
    .getByText("[Demo preview] Try distinguishing", { exact: false })
    .waitFor();
  assert.equal(turnCalls.at(-1).request_id, failedId);
  assert.equal(
    w.messages.filter(
      (m) => m.role === "user" && m.content.includes("FAIL_ONCE"),
    ).length,
    1,
  );
  assert.equal(await input.inputValue(), "");
  ok(
    "provider failure survives reload; same-ID retry avoids duplicate user message",
  );
  await shot("student-desktop");
  await page
    .getByRole("button", { name: "Progress & responses", exact: true })
    .click();
  await page.getByLabel("Edit saved response").waitFor();
  assert.match(
    await page.getByLabel("Edit saved response").inputValue(),
    /FAIL_ONCE/,
  );
  await page
    .getByLabel("Edit saved response")
    .fill("Saved response edited in the secondary panel");
  await page
    .getByRole("button", { name: "Save response", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      !document.querySelector("button[disabled]") ||
      document.body.innerText.includes("revision 2"),
  );
  assert.equal(w.attempts.q1.revision_count, 2);
  ok("secondary response editing preserves revision history");
  await page
    .getByRole("button", { name: "Request instructor example", exact: true })
    .click();
  await page
    .getByText("Synthetic instructor example:", { exact: false })
    .waitFor();
  assert.equal(w.attempts.q1.reference_revealed, true);
  ok("reference request stays separately gated and visible");
  await page.getByRole("button", { name: "Close learning panel" }).click();
  await input.fill(
    "Reliability means consistency across raters and occasions.",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page
    .getByText("Let us use the figures next.", { exact: false })
    .waitFor();
  await page
    .locator(".guided-message .guided-question-images img")
    .first()
    .waitFor();
  assert.equal(
    await page.locator(".guided-message .guided-question-images img").count(),
    3,
  );
  assert.equal(
    await page
      .locator(".guided-message .guided-question-images img")
      .evaluateAll((imgs) =>
        imgs.every((i) => i.complete && i.naturalWidth > 0),
      ),
    true,
  );
  ok("actual configured graph assets appear inside the conversation");
  await page.setViewportSize({ width: 390, height: 844 });
  const graph = page
    .locator(".guided-message .guided-question-images a")
    .last();
  await graph.click({ trial: true });
  const graphBox = await graph.boundingBox(),
    streamBox = await page.locator(".guided-stream").boundingBox();
  assert.ok(
    graphBox.y >= streamBox.y - 1 &&
      graphBox.y + graphBox.height <= streamBox.y + streamBox.height + 1,
  );
  await page.screenshot({
    path: path.join(OUT, "student-mobile.png"),
    fullPage: true,
  });
  screenshots.push(path.join(OUT, "student-mobile.png"));
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
    true,
  );
  await page.getByRole("button", { name: "Materials", exact: true }).click();
  await page.getByText("Synthetic student reading").waitFor();
  assert.equal(await page.locator(".guided-conversation").isVisible(), false);
  await shot("materials-mobile");
  await page.getByRole("button", { name: "Close learning panel" }).click();
  assert.equal(await input.isVisible(), true);
  ok(
    "390px materials panel and composer reachable without horizontal overflow",
  );
  await input.fill("A is positive; B shows no linear pattern; C is negative.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page
    .getByRole("button", { name: "Skip the quiz", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Skip the quiz", exact: true })
    .click();
  await page.getByText("Your conversation is saved", { exact: true }).waitFor();
  assert.equal(w.tutor.quiz.status, "skipped");
  ok("optional quiz can be declined without blocking required work");
  const downloading = page.waitForEvent("download");
  await page.getByLabel("Download conversation").click();
  await page.getByRole("link", { name: "Conversation · HTML" }).click();
  const download = await downloading;
  await download.saveAs(path.join(OUT, "download-observed.txt"));
  console.log(
    "DOWNLOAD",
    download.url(),
    download.suggestedFilename(),
    (await readFile(path.join(OUT, "download-observed.txt"), "utf8")).slice(
      0,
      400,
    ),
  );
  assert.match(
    await readFile(path.join(OUT, "download-observed.txt"), "utf8"),
    /Synthetic UI download fixture/,
  );
  assert.match(download.url(), /version_id=edition-1&format=html/);
  ok("download links point to pinned raw transcript endpoints");
  await page
    .getByRole("button", { name: "Submit for teacher review", exact: true })
    .click();
  await page.getByRole("dialog").waitFor();
  await page
    .getByRole("button", { name: "Submit worksheet", exact: true })
    .click();
  await page
    .getByText("Submitted for teacher review.", { exact: false })
    .first()
    .waitFor();
  assert.equal(w.submission.status, "submitted");
  assert.equal(await page.locator(".guided-composer").count(), 0);
  ok(
    "explicit submission locks conversation without teacher auto-confirmation",
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  viewer = {
    ...student,
    id: "ui-teacher",
    role: "teacher",
    name: "Synthetic teacher",
  };
  await page.goto(base + "/#/record/fixture-session/ui-student");
  await page.reload();
  await page
    .getByRole("button", { name: "Teacher review", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm completion", exact: true })
    .waitFor();
  await page
    .getByRole("textbox", { name: "Teacher note", exact: true })
    .fill("Synthetic teacher confirmation");
  await page
    .getByRole("button", { name: "Confirm completion", exact: true })
    .click();
  await page.getByText("Teacher confirmation saved.").waitFor();
  assert.equal(w.submission.status, "confirmed");
  await shot("teacher-observation");
  ok(
    "teacher observation stays read-only while authorized review remains available",
  );
  assert.deepEqual(pageErrors, []);
  status = "passed";
} catch (e) {
  failure = String(e.stack || e);
  console.error(failure);
  await shot("failure");
  process.exitCode = 1;
} finally {
  await writeFile(
    path.join(OUT, "result.json"),
    JSON.stringify(
      {
        status,
        evidence:
          "Synthetic frontend browser fixtures only; not actual backend or live model acceptance",
        checks,
        screenshots,
        pageErrors,
        failure,
        startCalls,
        turnRequests: turnCalls.length,
      },
      null,
      2,
    ),
  );
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
