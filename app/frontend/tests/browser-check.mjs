// Isolated UI exercise against EXPLICIT SYNTHETIC API FIXTURES.
// It is not a backend integration test and does not contact a model.
import { createServer } from "vite";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "..");
const artifacts = path.join(root, "tests", "artifacts");
await fs.mkdir(artifacts, { recursive: true });
const ai = {
  mode: "demo",
  configured: true,
  base_url: "",
  model: "explicit-fixture-demo",
  last_error: null,
};
const teacher = {
  id: "fixture-teacher",
  name: "Demo instructor",
  email: "teacher@example.invalid",
  role: "teacher",
};
const student = {
  id: "fixture-student",
  name: "Demo learner",
  email: "student@example.invalid",
  role: "student",
};
const admin = { ...teacher, id: "fixture-admin", role: "admin", is_demo: true };
let currentUser = null;
let fixtureVersions = [
  {
    id: "fixture-v1",
    number: 1,
    label: "Explicit baseline fixture",
    created_at: "2026-10-01T00:00:00Z",
    created_by: teacher.id,
  },
];
const course = {
  id: "fixture-course",
  code: "EDUC7703",
  title: "Language Testing & Assessment",
  description:
    "Explicit UI test fixture. Original course data is not used in this isolated check.",
  student_count: 2,
  join_code: "FIXTURE-ONLY",
};
const question = (id, group_id, ordinal, type = "open_response") => ({
  id,
  group_id,
  ordinal,
  type,
  prompt:
    type === "image_matching"
      ? "Compare these three synthetic scatter plots. Explain the pattern you see."
      : `Synthetic question ${ordinal}: explain a principle of assessment and give a classroom example.`,
  options:
    type === "single_choice"
      ? [
          "A contextual task",
          "An isolated word list",
          "A timed translation",
          "A recall exercise",
        ]
      : [],
  answer_slots: ordinal === 6 ? 3 : 1,
  images:
    type === "image_matching"
      ? ["A", "B", "C"].map((label) => ({
          label,
          url: `/api/assets/fixture-${label}.svg`,
          alt: `Synthetic scatter plot ${label}`,
        }))
      : [],
  source_label: "EXPLICIT TEST FIXTURE · not original course material",
});
const sessions = {
  "fixture-4": {
    id: "fixture-4",
    course_id: course.id,
    title: "What makes a good test?",
    subtitle: "Principles of language assessment · synthetic UI fixture",
    number: 4,
    status: "published",
    question_count: 22,
    estimated_minutes: 40,
    learning_objectives: [
      "Explain assessment quality using a classroom example.",
      "Compare validity, reliability and practical constraints.",
    ],
    instructions:
      "Explicit test instructions. Encourage a first attempt before revealing references.",
    reference_policy: "after_attempt",
    teaching_language: "en",
    groups: [
      { id: "T1", title: "Task 1 · Concepts", kind: "core" },
      { id: "T2", title: "Task 2 · Choices", kind: "core" },
      { id: "T3", title: "Task 3 · Scatter plots", kind: "core" },
      { id: "T4", title: "Task 4 · Reflection", kind: "core" },
    ],
    questions: Array.from({ length: 22 }, (_, i) =>
      question(
        `fixture-q${i + 1}`,
        i < 6 ? "T1" : i < 11 ? "T2" : i < 14 ? "T3" : "T4",
        i + 1,
        i < 6
          ? "fill_in_blank"
          : i < 11
            ? "single_choice"
            : i < 14
              ? "image_matching"
              : "open_response",
      ),
    ),
    materials: [
      {
        id: "fixture-material",
        title: "Synthetic teaching notes",
        kind: "slides",
        visibility: "student",
        status: "ready",
        source_label: "EXPLICIT FIXTURE",
        excerpt:
          "Synthetic teaching material for front-end layout verification.",
      },
    ],
  },
  "fixture-2": {
    id: "fixture-2",
    course_id: course.id,
    title: "Curriculum, examinations & washback",
    subtitle: "Core concepts and one guided reading · synthetic UI fixture",
    number: 2,
    status: "published",
    question_count: 19,
    estimated_minutes: 50,
    learning_objectives: [
      "Explain washback and the relationship between curriculum and assessment.",
    ],
    instructions: "Synthetic fixture only. Choose one reading.",
    reference_policy: "after_attempt",
    teaching_language: "en",
    groups: [
      { id: "I", title: "Part I · Core concepts", kind: "core" },
      { id: "II-Pong", title: "Pong & Chow", kind: "reading" },
      { id: "II-Bray", title: "Bray & Kwok", kind: "reading" },
    ],
    questions: [
      ...Array.from({ length: 9 }, (_, i) =>
        question(`fixture-core${i + 1}`, "I", i + 1),
      ),
      ...Array.from({ length: 5 }, (_, i) =>
        question(`fixture-pong${i + 1}`, "II-Pong", i + 1, "reading_response"),
      ),
      ...Array.from({ length: 5 }, (_, i) =>
        question(`fixture-bray${i + 1}`, "II-Bray", i + 1, "reading_response"),
      ),
    ],
    materials: [],
  },
};
for (const s of Object.values(sessions))
  s.reference_answers = Object.fromEntries(
    s.questions.map((q) => [
      q.id,
      `Synthetic teacher reference for ${q.id}. Not an original course answer.`,
    ]),
  );
const records = {};
function key(sid, user = currentUser) {
  return `${sid}:${user.id}`;
}
function workspace(sid, user = currentUser) {
  const s = sessions[sid];
  const k = key(sid, user);
  records[k] ??= {
    selected_reading: null,
    attempts: {},
    messages: [],
    submission: {
      status: "not_started",
      submitted_at: null,
      reviewed_at: null,
      teacher_note: "",
    },
  };
  const r = records[k];
  const ids = s.questions
    .filter(
      (q) =>
        s.groups.find((g) => g.id === q.group_id).kind === "core" ||
        q.group_id === r.selected_reading,
    )
    .map((q) => q.id);
  const clean = { ...s };
  if (user.role !== "teacher") delete clean.reference_answers;
  return {
    session: clean,
    user,
    ...r,
    progress: {
      answered: ids.filter((id) => r.attempts[id]?.answer).length,
      total: ids.length,
      active_question_ids: ids,
      current_question_id: ids.find((id) => !r.attempts[id]?.answer) || ids[0],
    },
    ai: { ...ai },
  };
}
function saveAnswer(sid, qid, answer) {
  const w = workspace(sid);
  const old = w.attempts[qid];
  w.attempts[qid] = {
    question_id: qid,
    answer,
    revision_count: (old?.revision_count || 0) + 1,
    updated_at: new Date().toISOString(),
    reference_revealed: old?.reference_revealed || false,
    revisions: [
      ...(old?.revisions || []),
      ...(old ? [{ answer: old.answer, created_at: old.updated_at }] : []),
    ],
  };
  w.submission.status = "in_progress";
}
const plugin = {
  name: "explicit-ui-fixture",
  transformIndexHtml(html) {
    return html.replace(
      "</body>",
      '<div id="fixture-disclosure" style="position:fixed;right:12px;bottom:8px;z-index:9999;padding:5px 8px;border:1px solid #d5966c;border-radius:5px;background:#fff3de;color:#8e4420;font:9px sans-serif;pointer-events:none">EXPLICIT UI FIXTURE · NOT BACKEND INTEGRATION</div></body>',
    );
  },
  configureServer(server) {
    server.middlewares.use(async (req, res, next) => {
      if (!req.url?.startsWith("/api/")) return next();
      let raw = "";
      for await (const c of req) raw += c;
      let body = {};
      if (raw && req.headers["content-type"]?.includes("application/json"))
        body = JSON.parse(raw);
      const url = new URL(req.url, "http://fixture");
      const p = url.pathname;
      const method = req.method;
      const send = (data, status = 200) => {
        res.statusCode = status;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(data));
      };
      if (p === "/api/bootstrap")
        return send({
          app_name: "AIcademiya (explicit fixture)",
          demo_enabled: true,
          default_locale: "en",
          ai,
        });
      if (p === "/api/auth/me")
        return currentUser
          ? send({ user: currentUser })
          : send({ detail: "Fixture: sign in required" }, 401);
      if (p === "/api/auth/demo") {
        currentUser =
          body.role === "admin"
            ? admin
            : body.role === "teacher"
              ? teacher
              : student;
        return send({ user: currentUser });
      }
      if (p === "/api/auth/logout") {
        currentUser = null;
        return send({ ok: true });
      }
      if (!currentUser)
        return send({ detail: "Fixture: sign in required" }, 401);
      if (p === "/api/courses") return send([course]);
      if (p === `/api/courses/${course.id}/sessions`)
        return send(
          Object.values(sessions).map((s) => ({
            ...s,
            student_status: workspace(s.id).submission.status,
          })),
        );
      if (p.startsWith("/api/assets/")) {
        res.setHeader("Content-Type", "image/svg+xml");
        return res.end(
          '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="140"><rect width="160" height="140" fill="white"/><path d="M20 15V120H145" fill="none" stroke="#333"/><g fill="#47684d">' +
            [0, 1, 2, 3, 4, 5, 6, 7, 8]
              .map(
                (i) =>
                  `<circle cx="${30 + i * 12}" cy="${100 - i * 8 + (i % 3) * 7}" r="3"/>`,
              )
              .join("") +
            '</g><text x="20" y="137" font-size="9">Synthetic test diagram</text></svg>',
        );
      }
      if (p === `/api/teacher/courses/${course.id}/versions/publish`) {
        const v = {
          id: `fixture-v${fixtureVersions.length + 1}`,
          number: fixtureVersions.length + 1,
          label: body.label,
          created_at: new Date().toISOString(),
          created_by: currentUser.id,
        };
        fixtureVersions.push(v);
        return send(v);
      }
      if (p === `/api/teacher/courses/${course.id}/versions`)
        return send({
          current_version_id: fixtureVersions.at(-1).id,
          has_unpublished_changes: true,
          versions: fixtureVersions,
        });
      if (p === "/api/teacher/settings") {
        if (currentUser.role !== "admin")
          return send(
            { detail: "Explicit fixture: administrator required" },
            403,
          );
        if (method === "PUT") {
          Object.assign(ai, body);
          delete ai.api_key;
          ai.configured = true;
        }
        return send({ ai, api_key_set: false });
      }
      if (p === "/api/teacher/settings/test")
        return send({
          ok: ai.mode === "demo",
          message:
            ai.mode === "demo"
              ? "Explicit fixture: deterministic demo test. No model was called."
              : "Explicit fixture: simulated connectivity rejection. Not a real connection test.",
          mode: ai.mode,
          model: ai.model,
        });
      const teacherMatch = p.match(
        /^\/api\/teacher\/sessions\/([^/]+)\/students(?:\/([^/]+)(?:\/(workspace|review|export))?)?$/,
      );
      if (teacherMatch) {
        const [, sid, uid, action] = teacherMatch;
        if (!uid) {
          const w = workspace(sid, student);
          return send([
            {
              user: student,
              answered: w.progress.answered,
              total: w.progress.total,
              selected_reading: w.selected_reading,
              status: w.submission.status,
              last_active: new Date().toISOString(),
              submitted_at: w.submission.submitted_at,
            },
          ]);
        }
        const w = workspace(sid, student);
        w.session = { ...sessions[sid] };
        if (action === "review") {
          w.submission.status = body.status;
          w.submission.teacher_note = body.note;
          w.submission.reviewed_at = new Date().toISOString();
        }
        return send(w);
      }
      const match = p.match(
        /^\/api\/sessions\/([^/]+)(?:\/(workspace|reading|chat|submit|export|answers|references|materials)(?:\/([^/]+))?)?$/,
      );
      if (match) {
        const [, sid, action, qid] = match;
        const s = sessions[sid];
        if (!s) return send({ detail: "Fixture session not found" }, 404);
        if (!action) {
          if (method === "PATCH") Object.assign(s, body);
          return send(s);
        }
        const w = workspace(sid);
        const r = records[key(sid)];
        if (action === "reading") r.selected_reading = body.group_id;
        if (action === "answers") saveAnswer(sid, qid, body.answer);
        if (action === "chat") {
          if (body.message === "FIXTURE_ERROR")
            return send(
              { detail: "Explicit fixture: model service unavailable" },
              502,
            );
          if (body.intent === "answer")
            saveAnswer(sid, body.question_id, body.message);
          r.messages.push(
            {
              id: `u-${r.messages.length}`,
              role: "user",
              content: body.message,
              question_id: body.question_id,
              created_at: new Date().toISOString(),
              mode: ai.mode,
              intent: body.intent,
            },
            {
              id: `a-${r.messages.length}`,
              role: "assistant",
              content:
                "Explicit deterministic UI fixture feedback. Consider how your example supports your claim, then revise if needed.",
              question_id: body.question_id,
              created_at: new Date().toISOString(),
              mode: ai.mode,
              citations: [
                {
                  source_label: "Synthetic fixture source",
                  text: "This is not a live model response.",
                },
              ],
            },
          );
        }
        if (action === "references") {
          if (!w.attempts[qid])
            return send({ detail: "Explicit fixture: attempt required" }, 409);
          w.attempts[qid].reference_revealed = true;
          return send({
            question_id: qid,
            reference: s.reference_answers[qid],
            source_label: "Synthetic teacher reference fixture",
          });
        }
        if (action === "submit") {
          if (
            w.progress.answered !== w.progress.total ||
            (s.groups.some((g) => g.kind === "reading") && !r.selected_reading)
          )
            return send(
              { detail: "Explicit fixture: complete active questions" },
              409,
            );
          r.submission.status = "submitted";
          r.submission.submitted_at = new Date().toISOString();
        }
        if (action === "materials") {
          const m = {
            id: "uploaded-fixture",
            title: "Uploaded synthetic test file",
            kind: "reading",
            visibility: "student",
            status: "needs_review",
            source_label: "Explicit upload fixture",
            excerpt: "Synthetic parsing preview.",
            warning: "Explicit fixture: review required.",
          };
          s.materials.push(m);
          return send(m);
        }
        return send(workspace(sid));
      }
      return send(
        { detail: `Unsupported explicit fixture route: ${method} ${p}` },
        501,
      );
    });
  },
};
const server = await createServer({
  configFile: path.join(root, "vite.config.ts"),
  root,
  plugins: [plugin],
  server: { host: "127.0.0.1", port: 18776, strictPort: true, watch: null },
});
let browser;
const checks = [];
const errors = [];
const shots = [];
try {
  await server.listen();
  // Use the installed Chrome; no global package or browser install.
  const chrome = "C:/Program Files/Google/Chrome/Application/chrome.exe";
  if (process.env.TMPDIR) {
    process.env.TEMP = process.env.TMPDIR;
    process.env.TMP = process.env.TMPDIR;
  }
  browser = await chromium.launch({ headless: true, executablePath: chrome });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.on("pageerror", (e) => errors.push(e.message));
  const shot = async (name) => {
    const target = path.join(artifacts, `${name}.png`);
    await page.screenshot({ path: target, fullPage: true });
    shots.push(target);
  };
  const check = async (name, fn) => {
    await fn();
    checks.push(name);
  };
  await page.addInitScript(() => {
    localStorage.setItem("akademiya.locale", "zh");
    localStorage.setItem("aicademiya.locale", "zh");
  });
  const englishOnly = async () => {
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator(".locale-button")).toHaveCount(0);
    await expect(
      page.getByRole("button", {
        name: /中文|English interface|Interface language/,
      }),
    ).toHaveCount(0);
  };
  await page.goto("http://127.0.0.1:18776/");
  await expect(
    page.getByRole("button", { name: "Try as student", exact: true }),
  ).toBeEnabled();
  await shot("fixture-login-desktop");
  await check(
    "Keyboard focus stays within the English login form",
    async () => {
      await page
        .getByRole("textbox", { name: "Email address", exact: true })
        .focus();
      await page.keyboard.press("Tab");
      await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
      await page.keyboard.press("Shift+Tab");
      await expect(
        page.getByRole("textbox", { name: "Email address", exact: true }),
      ).toBeFocused();
    },
  );
  await check(
    "Stored Chinese preferences do not change login language",
    async () => {
      await englishOnly();
      await expect(
        page.getByRole("button", { name: "Try as student", exact: true }),
      ).toBeVisible();
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Try as student", exact: true }),
      ).toBeEnabled();
      await englishOnly();
    },
  );
  await page
    .getByRole("button", { name: "Try as student", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Language Testing & Assessment",
      exact: true,
    }),
  ).toBeVisible();
  await shot("fixture-student-home");
  await page
    .getByRole("button", { name: "Open session", exact: true })
    .first()
    .click();
  await expect(page.locator("#question-select")).toBeVisible();
  await check(
    "English workspace labels preserve original teaching content after reload",
    async () => {
      await englishOnly();
      await page.reload();
      await expect(
        page.getByRole("heading", { name: "Learning dialogue", exact: true }),
      ).toBeVisible();
      await englishOnly();
      await expect(
        page.getByRole("button", { name: "Request reference", exact: true }),
      ).toBeDisabled();
      await expect(page.locator(".current-question h3")).toContainText(
        "Synthetic question 1",
      );
    },
  );
  await check(
    "Reference disabled before attempt; submit incomplete",
    async () => {
      await expect(
        page.getByRole("button", { name: "Request reference", exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByRole("button", { name: "Submit worksheet", exact: true }),
      ).toBeDisabled();
    },
  );
  await check("Answer intent saves; reference explicitly reveals", async () => {
    await page
      .getByRole("textbox", { name: "Answer this question", exact: true })
      .fill("An explicit synthetic test attempt.");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Request reference", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Request reference", exact: true })
      .click();
    await expect(
      page.getByText("Synthetic teacher reference for fixture-q1.", {
        exact: false,
      }),
    ).toBeVisible();
  });
  await check("Follow-up preserves saved answer", async () => {
    await page
      .getByRole("button", { name: "Ask a follow-up", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Ask a follow-up", exact: true })
      .fill("How can I explain my example?");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(
      page.getByRole("textbox", { name: "Revise saved answer", exact: true }),
    ).toHaveValue("An explicit synthetic test attempt.");
  });
  await check("Revision persists across reload", async () => {
    await page
      .getByRole("textbox", { name: "Revise saved answer", exact: true })
      .fill("A revised explicit synthetic test attempt.");
    await page
      .getByRole("button", { name: "Save answer only", exact: true })
      .click();
    await expect(
      page.getByText("Saved", { exact: true }).first(),
    ).toBeVisible();
    await page.reload();
    await page.locator("#question-select").selectOption("fixture-q1");
    await expect(
      page.getByRole("textbox", { name: "Revise saved answer", exact: true }),
    ).toHaveValue("A revised explicit synthetic test attempt.");
  });
  await page.locator("#question-select").selectOption("fixture-q12");
  await expect(page.locator(".question-images img")).toHaveCount(3);
  await shot("fixture-workspace-images");
  await check(
    "Visible error does not clear the draft or invent a reply",
    async () => {
      await page
        .getByRole("button", { name: "Ask a follow-up", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Ask a follow-up", exact: true })
        .fill("FIXTURE_ERROR");
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText(
        "Explicit fixture: model service unavailable",
      );
      await expect(
        page.getByRole("textbox", { name: "Ask a follow-up", exact: true }),
      ).toHaveValue("FIXTURE_ERROR");
    },
  );
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await check("Explicit submission of all 22 synthetic units", async () => {
    for (let i = 2; i <= 22; i++) {
      await page.locator("#question-select").selectOption(`fixture-q${i}`);
      await page
        .getByRole("textbox", { name: "Revise saved answer", exact: true })
        .fill(`Synthetic answer ${i}.`);
      await page
        .getByRole("button", { name: "Save answer only", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Save answer only", exact: true }),
      ).toBeDisabled();
    }
    await page
      .getByRole("button", { name: "Submit worksheet", exact: true })
      .click();
    await page
      .locator(".submit-confirm")
      .getByRole("button", { name: "Submit worksheet", exact: true })
      .click();
    await expect(page.locator(".workspace-heading .status")).toContainText(
      "Submitted",
    );
  });
  await page.goto("http://127.0.0.1:18776/#/workspace/fixture-2");
  await expect(
    page.getByText("Choose one reading", { exact: true }),
  ).toBeVisible();
  await check(
    "One S2 reading activates 14 units; branch switching retains answers",
    async () => {
      await page
        .getByRole("button", { name: "Pong & Chow", exact: false })
        .click();
      await expect(page.locator(".progress-block strong")).toContainText("14");
      await page.locator("#question-select").selectOption("fixture-pong1");
      await page
        .getByRole("textbox", { name: "Revise saved answer", exact: true })
        .fill("Pong branch fixture answer.");
      await page
        .getByRole("button", { name: "Save answer only", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Save answer only", exact: true }),
      ).toBeDisabled();
      if (
        !(await page
          .locator(".reading-selector details")
          .evaluate((el) => el.open))
      )
        await page.getByText("Choose one reading", { exact: true }).click();
      await page
        .getByRole("button", { name: "Bray & Kwok", exact: false })
        .click();
      await expect(page.locator(".progress-block strong")).toContainText("14");
      if (
        !(await page
          .locator(".reading-selector details")
          .evaluate((el) => el.open))
      )
        await page.getByText("Choose one reading", { exact: true }).click();
      await page
        .getByRole("button", { name: "Pong & Chow", exact: false })
        .click();
      await page.locator("#question-select").selectOption("fixture-pong1");
      await expect(
        page.getByRole("textbox", { name: "Revise saved answer", exact: true }),
      ).toHaveValue("Pong branch fixture answer.");
    },
  );
  await check("390px mobile worksheet has no horizontal overflow", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: /Worksheet ·/ }).click();
    const size = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      width: innerWidth,
    }));
    expect(size.scroll).toBeLessThanOrEqual(size.width);
    await shot("fixture-workspace-mobile");
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page
    .getByRole("button", { name: "Try as teacher", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Configure", exact: true })
    .first()
    .click();
  await check(
    "Teacher configuration saves via PATCH and reads back",
    async () => {
      await page
        .getByRole("textbox", { name: "Teaching instructions", exact: true })
        .fill("Explicit fixture: edited instructions from the actual UI.");
      await page
        .getByRole("button", { name: "Save changes", exact: true })
        .click();
      await expect(
        page.getByRole("textbox", {
          name: "Teaching instructions",
          exact: true,
        }),
      ).toHaveValue(
        "Explicit fixture: edited instructions from the actual UI.",
      );
      await page.reload();
      await expect(
        page.getByRole("textbox", {
          name: "Teaching instructions",
          exact: true,
        }),
      ).toHaveValue(
        "Explicit fixture: edited instructions from the actual UI.",
      );
    },
  );
  await shot("fixture-teacher-configuration");
  await check(
    "Teacher draft publication is explicitly course-version scoped",
    async () => {
      await page
        .locator(".tabs")
        .getByRole("button", { name: "Versions", exact: true })
        .click();
      await page
        .getByRole("button", {
          name: "Publish complete course draft",
          exact: true,
        })
        .click();
      await expect(page.getByText(/Course version 2 published/)).toBeVisible();
    },
  );
  await check("Teacher reference editing is saved and read back", async () => {
    await page
      .locator(".tabs")
      .getByRole("button", { name: "Questions & references", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Teacher reference response", exact: true })
      .first()
      .fill("Explicit fixture: revised teacher reference.");
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(
      page
        .getByRole("textbox", {
          name: "Teacher reference response",
          exact: true,
        })
        .first(),
    ).toHaveValue("Explicit fixture: revised teacher reference.");
  });
  await check(
    "Upload displays the fixture needs-review state and extraction warning",
    async () => {
      await page
        .locator(".tabs")
        .getByRole("button", { name: "Materials", exact: true })
        .click();
      await page.getByLabel("Choose a file", { exact: true }).setInputFiles({
        name: "explicit-fixture.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(
          "Explicit synthetic fixture upload. No actual course material.",
        ),
      });
      await page
        .getByRole("button", { name: "Upload material", exact: true })
        .click();
      await expect(
        page.getByText("Uploaded synthetic test file", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("Explicit fixture: review required.", { exact: true }),
      ).toBeVisible();
      await expect(page.locator(".material-status.needs_review")).toContainText(
        "Needs review",
      );
      await expect(
        page.getByLabel("Choose a file", { exact: true }),
      ).toHaveValue("");
    },
  );
  await shot("fixture-teacher-materials");
  await check(
    "Teacher sees original record and confirms submission",
    async () => {
      await page
        .locator(".tabs")
        .getByRole("button", { name: "Learning records", exact: true })
        .click();
      await page
        .getByRole("button", { name: "View record", exact: true })
        .click();
      await expect(
        page
          .getByText("An explicit synthetic test attempt.", { exact: true })
          .first(),
      ).toBeVisible();
      await page
        .getByRole("textbox", { name: "Feedback for the student", exact: true })
        .fill("Explicit fixture: confirmation note.");
      await page
        .getByRole("button", { name: "Confirm completion", exact: true })
        .click();
      await expect(page.locator(".workspace-heading .status")).toContainText(
        "Teacher confirmed",
      );
    },
  );
  await shot("fixture-teacher-record");
  await expect(
    page.getByRole("button", { name: "Model settings", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("button", { name: "Try as admin", exact: true }).click();
  await page
    .getByRole("button", { name: "Model settings", exact: true })
    .click();
  await check(
    "Model settings disclose demo/live and show a rejected fixture test",
    async () => {
      await page
        .getByRole("button", { name: /Live · OpenAI-compatible/ })
        .click();
      await page
        .getByRole("textbox", { name: "API base URL", exact: true })
        .fill("http://127.0.0.1:8000/v1");
      await page
        .getByRole("textbox", { name: "Model name", exact: true })
        .fill("explicit-fixture-model");
      await page
        .getByRole("button", { name: "Save changes", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Test saved connection",
          exact: true,
        }),
      ).toBeEnabled();
      await page
        .getByRole("button", { name: "Test saved connection", exact: true })
        .click();
      await expect(page.locator(".test-result.failed")).toContainText(
        "Explicit fixture: simulated connectivity rejection",
      );
    },
  );
  await shot("fixture-model-settings");
  expect(errors).toEqual([]);
  const result = {
    scope:
      "EXPLICIT FRONTEND FIXTURES ONLY — NOT REAL BACKEND OR MODEL INTEGRATION",
    checks,
    passed: checks.length,
    page_errors: errors,
    screenshots: shots,
  };
  await fs.writeFile(
    path.join(artifacts, "browser-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser?.close();
  await server.close();
}
