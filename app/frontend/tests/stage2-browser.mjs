// Explicit synthetic frontend HTTP fixtures. No backend/model evidence.
import { createServer } from "vite";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const artifacts = path.join(root, "artifacts", "stage2-fixtures");
await fs.mkdir(artifacts, { recursive: true });
const clone = (x) => structuredClone(x);
const ai = {
  mode: "demo",
  configured: true,
  base_url: "",
  model: "explicit-deterministic-fixture",
  web_search: { enabled: false, configured: false, provider: "tavily" },
};
const users = {
  student: {
    id: "synthetic-student",
    name: "Synthetic Student",
    email: "student@example.invalid",
    role: "student",
  },
  teacher: {
    id: "synthetic-teacher",
    name: "Synthetic Teacher",
    email: "teacher@example.invalid",
    role: "teacher",
  },
  admin: {
    id: "demo-admin",
    name: "Synthetic Administrator",
    email: "admin@example.invalid",
    role: "admin",
    is_demo: true,
  },
};
let current = null;
const course = {
  id: "synthetic-course",
  code: "SYNTHETIC",
  title: "Synthetic stage-2 course",
  description: "Explicit UI fixture; not backend integration.",
  student_count: 1,
  published_version_id: "v2",
  published_version_number: 2,
  has_unpublished_changes: false,
};
const q = (id = "q1") => ({
  id,
  group_id: "g1",
  ordinal: id === "q1" ? 1 : 2,
  type: "open_response",
  prompt: `Synthetic ${id} prompt`,
  options: [],
  answer_slots: 1,
  images: [],
  source_label: "Original synthetic worksheet page",
  source_material_ids: [],
  source_links: [],
});
let draft = {
  id: "s1",
  course_id: course.id,
  title: "Synthetic classroom",
  subtitle: "Contract UI fixture",
  number: 1,
  status: "published",
  question_count: 2,
  estimated_minutes: 10,
  learning_objectives: ["Explain synthetic evidence."],
  instructions: "Synthetic teaching instruction",
  reference_policy: "after_attempt",
  teaching_language: "en",
  active: true,
  starts_at: null,
  ends_at: null,
  effective_active: true,
  availability_reason: "manual_active",
  groups: [
    { id: "g1", title: "Core synthetic", kind: "core", description: "" },
  ],
  questions: [q(), q("q2")],
  reference_answers: {
    q1: "Synthetic reference one",
    q2: "Synthetic reference two",
  },
  materials: [
    {
      id: "m1",
      title: "Synthetic material",
      kind: "reading",
      visibility: "student",
      source_label: "Synthetic document",
      status: "ready",
      excerpt: "Synthetic extracted text only.",
      download_url: "/api/materials/m1/download",
      preview_url: "/api/materials/m1/preview",
      preview_kind: "text",
      url: null,
    },
  ],
};
let operational = {
  active: true,
  starts_at: null,
  ends_at: null,
  effective_active: true,
  availability_reason: "manual_active",
};
let editions = [
  {
    id: "v1",
    number: 1,
    label: "Original synthetic",
    created_at: "2026-10-01T00:00:00Z",
    created_by: "synthetic-teacher",
    course: clone(course),
    sessions: [clone(draft)],
  },
  {
    id: "v2",
    number: 2,
    label: "Current synthetic",
    created_at: "2026-10-02T00:00:00Z",
    created_by: "synthetic-teacher",
    course: clone(course),
    sessions: [clone(draft)],
  },
];
const runMap = new Map();
function ws(sid, vid, user = current) {
  const preview = user.role !== "student" && !vid;
  const version = preview
    ? { id: null, number: null, is_current: false, is_draft: true }
    : {
        id: vid || course.published_version_id,
        number:
          editions.find((v) => v.id === (vid || course.published_version_id))
            ?.number || 1,
        is_current:
          (vid || course.published_version_id) === course.published_version_id,
        is_draft: false,
      };
  const sidMissing = sid === "removed-session";
  let content = preview
    ? clone(draft)
    : clone(editions.find((v) => v.id === version.id)?.sessions[0] || draft);
  content = { ...content, ...operational };
  if (sidMissing) {
    content.id = sid;
    content.title = "Removed historical session";
    version.is_current = false;
  }
  const key = `${user.id}:${sid}:${version.id || "draft"}`;
  if (!runMap.has(key))
    runMap.set(key, {
      attempts: {},
      messages: [],
      selected_reading: null,
      submission: {
        status: "in_progress",
        submitted_at: null,
        reviewed_at: null,
        teacher_note: "",
      },
    });
  const r = runMap.get(key);
  const activeIds = content.questions
    .filter(
      (q) =>
        content.groups.find((g) => g.id === q.group_id)?.kind === "core" ||
        q.group_id === r.selected_reading,
    )
    .map((q) => q.id);
  if (user.role === "student") {
    delete content.reference_answers;
    content.instructions = "";
  }
  return {
    session: content,
    user: clone(user),
    ...clone(r),
    version,
    available_versions: editions.map(({ id, number, label }) => ({
      id,
      number,
      label,
    })),
    read_only:
      (!preview && !version.is_current) ||
      (!preview && !operational.effective_active),
    read_only_reason:
      !preview && !version.is_current
        ? "historical_version"
        : !operational.effective_active
          ? "session_inactive"
          : null,
    progress: {
      answered: activeIds.filter((id) => r.attempts[id]?.answer).length,
      total: activeIds.length,
      active_question_ids: activeIds,
      current_question_id: activeIds[0],
    },
    ai,
  };
}
function saveAnswer(sid, vid, qid, answer) {
  const w = ws(sid, vid);
  const r = runMap.get(`${current.id}:${sid}:${w.version.id || "draft"}`);
  const old = r.attempts[qid];
  r.attempts[qid] = {
    question_id: qid,
    answer,
    revision_count: (old?.revision_count || 0) + 1,
    updated_at: new Date().toISOString(),
    reference_revealed: old?.reference_revealed || false,
    revisions: old
      ? [
          ...(old.revisions || []),
          { answer: old.answer, created_at: old.updated_at },
        ]
      : [],
  };
}
let archived = false;
let rosterActionGate = null;
let roster = [
  { user: users.student, archived_at: null, purge_at: null, has_work: true },
];
let teachers = [clone(users.teacher)];
const calls = [];
let worksheetPreviewed = false;
const server = await createServer({
  root,
  configFile: path.join(root, "vite.config.ts"),
  server: { host: "127.0.0.1", port: 18778, strictPort: true, watch: null },
  plugins: [
    {
      name: "explicit-stage2-fixture",
      transformIndexHtml(html) {
        return html.replace(
          "</body>",
          '<div style="position:fixed;bottom:0;right:0;z-index:99999;background:#fff3de;padding:4px;font:10px sans-serif;pointer-events:none">SYNTHETIC HTTP FIXTURE · NO MODEL / BACKEND EVIDENCE</div></body>',
        );
      },
    },
  ],
});
let browser;
const checks = [];
const errors = [];
async function fixture(route) {
  const req = route.request();
  const u = new URL(req.url());
  const p = u.pathname,
    method = req.method(),
    vid = u.searchParams.get("version_id");
  let body = {};
  if (req.headers()["content-type"]?.includes("application/json"))
    body = req.postDataJSON() || {};
  calls.push({
    path: p,
    method,
    version: vid,
    body: body.default_temporary_password ? "[redacted]" : clone(body),
  });
  const send = (data, status = 200) =>
    route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  if (p === "/api/bootstrap")
    return send({
      app_name: "AIcademiya explicit fixture",
      demo_enabled: true,
      default_locale: "en",
      ai,
    });
  if (p === "/api/auth/demo") {
    current = clone(users[body.role]);
    return send({ user: current });
  }
  if (p === "/api/auth/me")
    return current
      ? send({ user: current })
      : send({ detail: "Synthetic sign-in required" }, 401);
  if (p === "/api/auth/logout") {
    current = null;
    return send({ ok: true });
  }
  if (!current) return send({ detail: "Synthetic sign-in required" }, 401);
  if (p === "/api/auth/profile") {
    current.name = body.name;
    return send({ user: current });
  }
  if (p === "/api/auth/change-password") {
    if (body.current_password !== "SyntheticCurrent123")
      return send({ detail: "Synthetic current password rejected" }, 403);
    return send({ user: current });
  }
  if (p === "/api/courses") return send([course]);
  if (p === `/api/courses/${course.id}/sessions`)
    return send([{ ...draft, ...operational }]);
  if (p === "/api/history")
    return send([
      {
        course: { id: course.id, code: course.code, title: course.title },
        session: {
          id: "removed-session",
          title: "Removed historical session",
          number: 0,
        },
        version: { id: "v1", number: 1, label: "Original synthetic" },
        status: "in_progress",
        answered: 0,
        total: 2,
        last_active: "2026-10-01T00:00:00Z",
      },
    ]);
  if (p === "/api/admin/teachers") return send(teachers);
  if (p === "/api/admin/teachers/synthetic-teacher/promote") {
    teachers = [];
    return send({ user: { ...users.teacher, role: "admin" } });
  }
  if (p === "/api/teacher/settings") {
    return current.role === "admin"
      ? send({ ai, api_key_set: false })
      : send({ detail: "Admin only" }, 403);
  }
  if (p === "/api/materials/m1/preview")
    return route.fulfill({
      contentType: "text/plain",
      body: "Synthetic authenticated preview text.",
    });
  const versions = p.match(
    /^\/api\/teacher\/courses\/([^/]+)\/versions(?:\/([^/]+)(?:\/(diff|restore))?)?$/,
  );
  if (versions) {
    const [, cid, v, action] = versions;
    if (v === "publish" || action === "restore") {
      const number = editions.length + 1;
      const next = {
        id: `v${number}`,
        number,
        label: body.label || "Synthetic new edition",
        created_at: new Date().toISOString(),
        created_by: current.id,
        course: clone(course),
        sessions:
          action === "restore"
            ? clone(editions.find((e) => e.id === v).sessions)
            : [clone(draft)],
      };
      editions.push(next);
      course.published_version_id = next.id;
      course.published_version_number = number;
      course.has_unpublished_changes = false;
      if (action === "restore")
        draft = { ...clone(next.sessions[0]), ...operational };
      return send(next);
    }
    if (action === "diff")
      return send({
        changes: [
          {
            path: "sessions/s1/questions/q1/prompt",
            before: "Original synthetic question",
            after: draft.questions[0].prompt,
          },
        ],
      });
    if (v) return send(editions.find((e) => e.id === v));
    return send({
      current_version_id: course.published_version_id,
      has_unpublished_changes: course.has_unpublished_changes,
      versions: editions.map(
        ({ id, number, label, created_at, created_by }) => ({
          id,
          number,
          label,
          created_at,
          created_by,
        }),
      ),
    });
  }
  const rosterRoute = p.match(
    /^\/api\/(?:teacher\/courses\/[^/]+\/students|admin\/students)(?:\/(archive|restore|import)(?:\/([^/]+)(?:\/(commit))?)?)?$/,
  );
  if (rosterRoute) {
    const [, action, importId, commit] = rosterRoute;
    if (action === "import") {
      if (commit) {
        roster.push({
          user: {
            id: "synthetic-import",
            name: "Synthetic Import",
            email: "import@example.invalid",
            role: "student",
          },
          archived_at: null,
          purge_at: null,
          has_work: false,
        });
        return send({ created: 1, enrolled: 0, restored: 0, skipped: 0 });
      }
      return send({
        import_id: "synthetic-import",
        rows: [
          {
            row_number: 2,
            name: "Synthetic Import",
            email: "import@example.invalid",
            action: "create",
            errors: [],
            warnings: ["Synthetic warning only"],
          },
        ],
        valid_count: 1,
        error_count: 0,
      });
    }
    if (action) {
      if (rosterActionGate) await rosterActionGate;
      archived = action === "archive";
      roster = roster.map((r) =>
        body.user_ids.includes(r.user.id)
          ? {
              ...r,
              archived_at: archived ? new Date().toISOString() : null,
              purge_at: archived
                ? new Date(Date.now() + 30 * 86400000).toISOString()
                : null,
            }
          : r,
      );
      return send({ affected_ids: body.user_ids });
    }
    return send(
      roster.filter(
        (r) =>
          Boolean(r.archived_at) ===
          (u.searchParams.get("archived") === "true"),
      ),
    );
  }
  const studentRecord = p.match(
    /^\/api\/teacher\/sessions\/([^/]+)\/students(?:\/([^/]+)\/(workspace|review))?$/,
  );
  if (studentRecord) {
    const [, sid, uid, action] = studentRecord;
    if (!uid) {
      const w = ws(sid, vid, users.student);
      return send([
        {
          user: users.student,
          answered: w.progress.answered,
          total: w.progress.total,
          status: w.submission.status,
          selected_reading: null,
          last_active: new Date().toISOString(),
          submitted_at: null,
          version: w.version,
        },
      ]);
    }
    return send(ws(sid, vid, users.student));
  }
  const match = p.match(
    /^\/api\/sessions\/([^/]+)(?:\/(workspace|chat|answers|references|reading|submit|materials|worksheet-import)(?:\/([^/]+)(?:\/(commit))?)?)?$/,
  );
  if (match) {
    const [, sid, action, id, commit] = match;
    if (!action) {
      if (method === "PATCH") {
        Object.assign(draft, body);
        if ("active" in body) {
          operational = {
            ...operational,
            ...body,
            effective_active:
              body.starts_at || body.ends_at
                ? (!body.starts_at ||
                    Date.now() >= Date.parse(body.starts_at)) &&
                  (!body.ends_at || Date.now() < Date.parse(body.ends_at))
                : body.active,
            availability_reason:
              body.starts_at || body.ends_at
                ? "scheduled"
                : body.active
                  ? "manual_active"
                  : "manual_inactive",
          };
        } else course.has_unpublished_changes = true;
        draft.question_count = draft.questions.length;
      }
      return send({ ...draft, ...operational });
    }
    if (action === "worksheet-import") {
      if (commit) {
        draft.groups =
          body.mode === "append"
            ? [...draft.groups, ...body.groups]
            : body.groups;
        draft.questions =
          body.mode === "append"
            ? [...draft.questions, ...body.questions]
            : body.questions;
        draft.reference_answers = {
          ...draft.reference_answers,
          ...body.reference_answers,
        };
        course.has_unpublished_changes = true;
        return send(draft);
      }
      worksheetPreviewed = true;
      return send({
        import_id: "worksheet-synthetic",
        material: { ...draft.materials[0], id: "worksheet-import" },
        draft: {
          title: "Extracted synthetic worksheet",
          groups: [
            { id: "import-g", title: "Imported synthetic group", kind: "core" },
          ],
          questions: [
            {
              ...q("import-q"),
              group_id: "import-g",
              prompt: "Imported synthetic prompt",
            },
          ],
          reference_answers: { "import-q": "Synthetic imported reference" },
        },
        warnings: [
          "Explicit fixture extraction warning; not a parser/model test.",
        ],
        method: "synthetic HTTP fixture",
        assets: [],
        needs_review: true,
      });
    }
    if (action === "materials") {
      if (method === "POST" && !id) {
        const multipart = req.postDataBuffer()?.toString("utf8") || "";
        const field = (name) =>
          multipart.match(
            new RegExp('name="' + name + '"\r\n\r\n([^\r\n]*)'),
          )?.[1];
        const material = {
          ...clone(draft.materials[0]),
          id: "synthetic-upload",
          title: "Synthetic uploaded notes",
          kind: field("kind"),
          visibility: field("visibility"),
          source_label: "Synthetic upload fixture; not parser evidence",
        };
        draft.materials.push(material);
        return send(material);
      }
      if (id === "link") {
        const m = {
          ...draft.materials[0],
          id: `link-${draft.materials.length}`,
          title: body.title || "Synthetic Link",
          kind: "link",
          url: body.url,
          visibility: body.visibility,
          preview_kind: "link",
          warning: "Synthetic no-body warning",
        };
        draft.materials.push(m);
        return send(m);
      }
      if (method === "PATCH") {
        const m = draft.materials.find((m) => m.id === id);
        Object.assign(m, body);
        return send(m);
      }
      if (method === "DELETE") {
        draft.materials = draft.materials.filter((m) => m.id !== id);
        return send({ ok: true });
      }
    }
    const w = ws(sid, vid);
    if (action === "answers") {
      if (w.read_only) return send({ detail: "Read only" }, 409);
      saveAnswer(sid, vid, id, body.answer);
      return send(ws(sid, vid));
    }
    if (action === "chat") {
      if (body.message === "SYNTHETIC_FAIL")
        return send(
          { detail: "Explicit synthetic provider failure; no model called" },
          502,
        );
      if (w.read_only) return send({ detail: "Read only" }, 409);
      const r = runMap.get(`${current.id}:${sid}:${w.version.id || "draft"}`);
      if (body.intent === "answer")
        saveAnswer(sid, vid, body.question_id, body.message);
      r.messages.push(
        {
          id: `msg-${r.messages.length}`,
          role: "user",
          content: body.message,
          question_id: body.question_id,
          created_at: new Date().toISOString(),
          mode: "demo",
          intent: body.intent,
        },
        {
          id: `reply-${r.messages.length}`,
          role: "assistant",
          content:
            "Explicit deterministic UI fixture feedback. No model called.",
          question_id: body.question_id,
          created_at: new Date().toISOString(),
          mode: "demo",
        },
      );
      return send(ws(sid, vid));
    }
    if (action === "references") {
      const key = `${current.id}:${sid}:${w.version.id || "draft"}`;
      const r = runMap.get(key);
      if (!r.attempts[id]?.answer)
        return send({ detail: "Attempt required" }, 409);
      r.attempts[id].reference_revealed = true;
      return send({
        question_id: id,
        reference: "Synthetic reference",
        source_label: "Synthetic",
      });
    }
    return send(w);
  }
  return send({ detail: `Unsupported fixture: ${method} ${p}` }, 501);
}
const check = async (name, fn) => {
  await fn();
  checks.push(name);
};
try {
  await server.listen();
  if (process.env.TMPDIR) {
    process.env.TEMP = process.env.TMPDIR;
    process.env.TMP = process.env.TMPDIR;
  }
  browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", fixture);
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
    await expect(page.locator(".brand")).toContainText("AIcademiya");
  };
  await page.goto("http://127.0.0.1:18778/");
  await check(
    "Stored Chinese UI preferences cannot change English login or branding",
    async () => {
      await expect(
        page.getByRole("heading", {
          name: "Your learning starts here.",
          exact: true,
        }),
      ).toBeVisible();
      await englishOnly();
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Try as student", exact: true }),
      ).toBeEnabled();
      await englishOnly();
      await page.screenshot({
        path: path.join(artifacts, "login-english.png"),
        fullPage: true,
      });
    },
  );
  await check(
    "First-password gate remains English-only without course navigation",
    async () => {
      current = { ...clone(users.student), must_change_password: true };
      await page.reload();
      await expect(
        page.getByRole("heading", {
          name: "Make this account yours.",
          exact: true,
        }),
      ).toBeVisible();
      await englishOnly();
      await expect(page.locator('input[type="password"]')).toHaveCount(3);
      await expect(page.locator(".sidebar")).toHaveCount(0);
      await page.screenshot({
        path: path.join(artifacts, "password-gate-english.png"),
        fullPage: true,
      });
      current = null;
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Try as student", exact: true }),
      ).toBeEnabled();
    },
  );
  await check("Original SVG branding and synthetic admin entry", async () => {
    await expect(page.locator(".brand")).toContainText("AIcademiya");
    await expect(page.locator("link[rel=icon]")).toHaveAttribute(
      "href",
      "/favicon.svg",
    );
    await expect(
      page.getByRole("button", { name: "Try as admin", exact: true }),
    ).toBeVisible();
  });
  await page
    .getByRole("button", { name: "Try as student", exact: true })
    .click();
  await page.getByRole("button", { name: "Open session", exact: true }).click();
  await check(
    "Version-aware chat and answer drafts survive reload and intent switching",
    async () => {
      await page
        .getByRole("textbox", { name: "Answer this question", exact: true })
        .fill("Unsent answer-intent draft");
      await page
        .getByRole("textbox", { name: "Revise saved answer", exact: true })
        .fill("Unsaved answer-pane draft");
      await page
        .getByRole("button", { name: "Ask a follow-up", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Ask a follow-up", exact: true })
        .fill("Unsent ask-intent draft");
      await page.reload();
      await expect(
        page.getByRole("textbox", {
          name: "Answer this question",
          exact: true,
        }),
      ).toHaveValue("Unsent answer-intent draft");
      await expect(
        page.getByRole("textbox", { name: "Revise saved answer", exact: true }),
      ).toHaveValue("Unsaved answer-pane draft");
      await page
        .getByRole("button", { name: "Ask a follow-up", exact: true })
        .click();
      await expect(
        page.getByRole("textbox", { name: "Ask a follow-up", exact: true }),
      ).toHaveValue("Unsent ask-intent draft");
      await englishOnly();
      expect(
        await page.evaluate(() => localStorage.getItem("akademiya.locale")),
      ).toBe("zh");
    },
  );
  await check("Question navigation isolates local drafts", async () => {
    await page.locator("#question-select").selectOption("q2");
    await expect(
      page.getByRole("textbox", { name: "Ask a follow-up", exact: true }),
    ).toHaveValue("");
    await expect(
      page.getByRole("textbox", { name: "Revise saved answer", exact: true }),
    ).toHaveValue("");
    await page.locator("#question-select").selectOption("q1");
    await expect(
      page.getByRole("textbox", { name: "Ask a follow-up", exact: true }),
    ).toHaveValue("Unsent ask-intent draft");
  });
  await check(
    "Failed chat keeps unsent draft and reports truthful error",
    async () => {
      await page
        .getByRole("textbox", { name: "Ask a follow-up", exact: true })
        .fill("SYNTHETIC_FAIL");
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText(
        "Explicit synthetic provider failure",
      );
      await page.reload();
      await page
        .getByRole("button", { name: "Ask a follow-up", exact: true })
        .click();
      await expect(
        page.getByRole("textbox", { name: "Ask a follow-up", exact: true }),
      ).toHaveValue("SYNTHETIC_FAIL");
    },
  );
  await check(
    "Successful save/send clears only its own draft and pins version_id",
    async () => {
      await page
        .getByRole("button", { name: "Save answer only", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Save answer only", exact: true }),
      ).toBeDisabled();
      await page
        .getByRole("textbox", { name: "Ask a follow-up", exact: true })
        .fill("Successful synthetic followup");
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(
        page.getByRole("textbox", { name: "Ask a follow-up", exact: true }),
      ).toHaveValue("");
      await page
        .getByRole("button", { name: "Answer this question", exact: true })
        .click();
      await expect(
        page.getByRole("textbox", {
          name: "Answer this question",
          exact: true,
        }),
      ).toHaveValue("Unsent answer-intent draft");
      expect(
        calls
          .filter((x) =>
            ["/api/sessions/s1/chat", "/api/sessions/s1/answers/q1"].includes(
              x.path,
            ),
          )
          .every((x) => x.version === "v2"),
      ).toBe(true);
    },
  );
  await check(
    "Inactive current classroom preserves drafts/history but disables all student composers",
    async () => {
      operational.active = false;
      operational.effective_active = false;
      operational.availability_reason = "manual_inactive";
      await page.reload();
      await expect(page.locator(".composer")).toHaveCount(0);
      await expect(
        page.getByRole("textbox", { name: "Revise saved answer", exact: true }),
      ).toHaveCount(0);
      await expect(
        page
          .getByRole("link", { name: "Export original record", exact: true })
          .first(),
      ).toBeVisible();
      operational.active = true;
      operational.effective_active = true;
      operational.availability_reason = "manual_active";
      await page.reload();
      await expect(
        page.getByRole("textbox", {
          name: "Answer this question",
          exact: true,
        }),
      ).toHaveValue("Unsent answer-intent draft");
    },
  );
  await check(
    "Historical edition is readonly while current draft remains recoverable",
    async () => {
      await page
        .getByLabel("Content edition", { exact: true })
        .selectOption("v1");
      await expect(page.locator(".composer")).toHaveCount(0);
      await expect(
        page.getByText("Historical · read-only", { exact: true }),
      ).toBeVisible();
      await page
        .getByLabel("Content edition", { exact: true })
        .selectOption("v2");
      await expect(
        page.getByRole("textbox", {
          name: "Answer this question",
          exact: true,
        }),
      ).toHaveValue("Unsent answer-intent draft");
    },
  );
  await check(
    "History opens sessions removed from the current edition",
    async () => {
      await page
        .getByRole("button", { name: "My learning", exact: true })
        .click();
      await page
        .getByRole("button", { name: /Removed historical session/ })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Removed historical session",
          exact: true,
        }),
      ).toBeVisible();
      expect(page.url()).toContain("version_id=v1");
    },
  );
  await check(
    "Student denied admin routes without fetching admin-only settings",
    async () => {
      const count = calls.filter(
        (c) => c.path === "/api/teacher/settings",
      ).length;
      await page.goto("http://127.0.0.1:18778/#/settings");
      await expect(page.getByRole("alert")).toContainText(
        "not available to your role",
      );
      expect(
        calls.filter((c) => c.path === "/api/teacher/settings").length,
      ).toBe(count);
      await expect(
        page.getByRole("button", { name: "Model settings", exact: true }),
      ).toHaveCount(0);
    },
  );
  await check("Bottom-avatar profile reads back display name", async () => {
    await page
      .getByRole("button", { name: "User Profile", exact: true })
      .click();
    await page
      .getByLabel("Full name", { exact: true })
      .fill("Synthetic Renamed");
    await page
      .locator(".profile-page")
      .getByRole("button", { name: "Save changes", exact: true })
      .first()
      .click();
    await expect(page.locator(".profile-entry")).toContainText(
      "Synthetic Renamed",
    );
  });
  await check(
    "Profile current/new/confirm password validates current password and reads back user",
    async () => {
      await page
        .getByLabel("Current password", { exact: true })
        .fill("SyntheticWrong123");
      await page
        .getByLabel("New password", { exact: true })
        .fill("SyntheticNew123");
      await page
        .getByLabel("Repeat new password", { exact: true })
        .fill("SyntheticNew123");
      await page
        .locator(".profile-page")
        .getByRole("button", { name: "Save changes", exact: true })
        .last()
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "Synthetic current password rejected",
      );
      await page
        .getByLabel("Current password", { exact: true })
        .fill("SyntheticCurrent123");
      await page
        .locator(".profile-page")
        .getByRole("button", { name: "Save changes", exact: true })
        .last()
        .click();
      await expect(
        page.getByLabel("Current password", { exact: true }),
      ).toHaveValue("");
    },
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page
    .getByRole("button", { name: "Try as teacher", exact: true })
    .click();
  await page.getByRole("button", { name: "Configure", exact: true }).click();
  await check(
    "Teacher tab order, model isolation and source editor",
    async () => {
      await expect(
        page
          .locator(".tabs")
          .getByRole("button", { name: "Configuration", exact: true }),
      ).toBeVisible();
      const labels = await page.locator(".tabs button").allTextContents();
      expect(labels.slice(0, 3)).toEqual([
        "Configuration",
        "Materials",
        "Questions & references",
      ]);
      await expect(
        page.getByRole("button", { name: "Model settings", exact: true }),
      ).toHaveCount(0);
      await page
        .locator(".tabs")
        .getByRole("button", { name: "Questions & references", exact: true })
        .click();
      await expect(
        page.getByText(/All materials · no selection/).first(),
      ).toBeVisible();
      await page.locator(".source-material-picker summary").first().click();
      await page
        .getByLabel("Synthetic material", { exact: false })
        .first()
        .check();
      await page
        .getByPlaceholder("https://… / 10.1234/example")
        .first()
        .fill("10.1234/synthetic");
      await page
        .getByRole("button", { name: "Add source", exact: true })
        .first()
        .click();
      await page
        .getByRole("button", { name: "Save content draft", exact: true })
        .click();
      await expect(
        page.getByLabel("Authored source", { exact: true }).first(),
      ).toHaveValue("10.1234/synthetic");
      const save = calls
        .filter((c) => c.path === "/api/sessions/s1" && c.method === "PATCH")
        .at(-1);
      expect(save.body.questions[0].source_material_ids).toEqual(["m1"]);
      expect(save.body.questions[0].source_label).toBe(
        "Original synthetic worksheet page",
      );
    },
  );
  await check(
    "Source removal restores all-material semantics and preserves original provenance",
    async () => {
      const source = page.locator(".source-editor").first();
      await source.getByRole("button", { name: "Remove", exact: true }).click();
      await expect(
        source.getByLabel("Authored source", { exact: true }),
      ).toHaveCount(0);
      await source
        .getByRole("button", { name: "Use all materials", exact: true })
        .click();
      await expect(
        source.getByText(/All materials · no selection/),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Save content draft", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Save content draft", exact: true }),
      ).toBeDisabled();
      const saved = calls
        .filter((c) => c.path === "/api/sessions/s1" && c.method === "PATCH")
        .at(-1);
      expect(saved.body.questions[0].source_material_ids).toEqual([]);
      expect(saved.body.questions[0].source_links).toEqual([]);
      expect(saved.body.questions[0].source_label).toBe(
        "Original synthetic worksheet page",
      );
      expect(draft.materials.some((m) => m.id === "m1")).toBe(true);
    },
  );
  await check(
    "Add/edit/reorder/delete arbitrary groups and questions",
    async () => {
      await page
        .getByRole("button", { name: "Add group", exact: true })
        .click();
      const group = page.locator(".group-editor").last();
      await group
        .getByLabel("Title", { exact: true })
        .fill("Custom synthetic reading");
      await group.locator("select").selectOption("reading");
      await page
        .getByRole("button", { name: "Add question", exact: true })
        .click();
      const question = page.locator(".question-edit-card").last();
      await question
        .getByLabel("Question prompt", { exact: true })
        .fill("New synthetic prompt");
      const gid = await group.locator("code").textContent();
      await question.getByLabel("Group", { exact: true }).selectOption(gid);
      await question
        .getByLabel("Options (one per line)", { exact: true })
        .fill("First\nSecond");
      await question
        .getByLabel("Teacher reference response", { exact: true })
        .fill("New synthetic reference");
      await question.getByRole("button", { name: /Move question up/ }).click();
      await page
        .getByRole("button", { name: "Save content draft", exact: true })
        .click();
      expect(
        draft.questions.find((q) => q.prompt === "New synthetic prompt")
          .options,
      ).toEqual(["First", "Second"]);
      await page
        .locator(".group-editor")
        .last()
        .getByRole("button", { name: "Delete group", exact: true })
        .click();
      await page
        .locator(".confirmation")
        .getByRole("button", { name: "Delete", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Save content draft", exact: true })
        .click();
      expect(draft.questions).toHaveLength(2);
    },
  );
  await check(
    "Worksheet extraction warning, review gate and structured commit",
    async () => {
      await page.getByLabel("Worksheet file", { exact: true }).setInputFiles({
        name: "synthetic.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Synthetic worksheet fixture"),
      });
      await page
        .getByRole("button", { name: "Extract preview", exact: true })
        .click();
      await expect(
        page.getByText(
          "Explicit fixture extraction warning; not a parser/model test.",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "Save reviewed content draft",
          exact: true,
        }),
      ).toBeDisabled();
      await page
        .getByLabel(
          "I reviewed the extracted questions, references and figures.",
          { exact: true },
        )
        .check();
      await page
        .getByRole("button", {
          name: "Save reviewed content draft",
          exact: true,
        })
        .click();
      await expect(page.getByText(/Reviewed worksheet saved/)).toBeVisible();
      expect(worksheetPreviewed).toBe(true);
      expect(draft.questions.some((q) => q.id === "import-q")).toBe(true);
    },
  );
  await page
    .locator(".tabs")
    .getByRole("button", { name: "Materials", exact: true })
    .click();
  await check(
    "Authenticated material text preview and manual Link management",
    async () => {
      await page
        .getByRole("button", { name: "Preview material", exact: true })
        .first()
        .click();
      await expect(page.locator(".preview-text")).toContainText(
        "Synthetic authenticated preview text.",
      );
      await page
        .getByRole("button", { name: "Close preview", exact: true })
        .click();
      const uploadForm = page.locator(".material-create-grid form").nth(0);
      const linkForm = page.locator(".material-create-grid form").nth(1);
      await uploadForm
        .getByLabel("Material type", { exact: true })
        .selectOption("slides");
      await uploadForm
        .getByLabel("Who can view it?", { exact: true })
        .selectOption("teacher");
      await expect(
        linkForm.getByLabel("Who can view it?", { exact: true }),
      ).toHaveValue("student");
      await uploadForm
        .getByLabel("Choose a file", { exact: true })
        .setInputFiles({
          name: "synthetic-notes.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("Synthetic upload text only."),
        });
      await uploadForm
        .getByRole("button", { name: "Upload material", exact: true })
        .click();
      await expect(
        page.getByText("Synthetic uploaded notes", { exact: true }),
      ).toBeVisible();
      await expect(
        uploadForm.getByLabel("Material type", { exact: true }),
      ).toHaveValue("slides");
      await expect(
        uploadForm.getByLabel("Who can view it?", { exact: true }),
      ).toHaveValue("teacher");
      await expect(
        linkForm.getByLabel("Who can view it?", { exact: true }),
      ).toHaveValue("student");
      expect(
        draft.materials.find((m) => m.id === "synthetic-upload"),
      ).toMatchObject({ kind: "slides", visibility: "teacher" });
      await page
        .getByLabel("URL / DOI", { exact: true })
        .fill("https://example.invalid/synthetic");
      await page
        .locator(".material-create-grid")
        .getByLabel("Title", { exact: true })
        .fill("Synthetic source Link");
      await page
        .getByRole("button", { name: "Save Link", exact: true })
        .click();
      await expect(
        page.getByRole("link", { name: "Open source link", exact: true }),
      ).toHaveAttribute("rel", "noopener noreferrer");
      await expect(
        page.getByText("Synthetic no-body warning", { exact: true }),
      ).toBeVisible();
      const savedLink = calls
        .filter(
          (c) =>
            c.path === "/api/sessions/s1/materials/link" && c.method === "POST",
        )
        .at(-1);
      expect(savedLink.body.visibility).toBe("student");
      await expect(
        uploadForm.getByLabel("Material type", { exact: true }),
      ).toHaveValue("slides");
      await expect(
        uploadForm.getByLabel("Who can view it?", { exact: true }),
      ).toHaveValue("teacher");
      await expect(
        linkForm.getByLabel("Who can view it?", { exact: true }),
      ).toHaveValue("student");
    },
  );
  await page
    .locator(".tabs")
    .getByRole("button", { name: "Configuration", exact: true })
    .click();
  await check(
    "Immediate operational closure independent of content publication",
    async () => {
      await page
        .getByLabel("Manually active (used only without a schedule)", {
          exact: true,
        })
        .uncheck();
      await page
        .getByRole("button", { name: "Apply availability now", exact: true })
        .click();
      await expect(
        page.getByText("Availability saved and read back.", { exact: true }),
      ).toBeVisible();
      expect(operational.effective_active).toBe(false);
      await page
        .getByLabel("Starts at (inclusive)", { exact: true })
        .fill("2020-01-01T00:00");
      await page
        .getByLabel("Ends at (exclusive)", { exact: true })
        .fill("2099-01-01T00:00");
      await expect(
        page.getByLabel("Manually active (used only without a schedule)", {
          exact: true,
        }),
      ).toBeDisabled();
      await page
        .getByRole("button", { name: "Apply availability now", exact: true })
        .click();
      expect(operational.effective_active).toBe(true);
      const update = calls
        .filter((c) => c.path === "/api/sessions/s1" && c.method === "PATCH")
        .at(-1);
      expect(Object.keys(update.body).sort()).toEqual([
        "active",
        "ends_at",
        "starts_at",
      ]);
      expect(update.body.starts_at).toMatch(/Z$/);
    },
  );
  await page
    .locator(".tabs")
    .getByRole("button", { name: "Versions", exact: true })
    .click();
  await check(
    "Course publish, readable diff, immutable snapshot and restore creates new version",
    async () => {
      await page
        .getByLabel("Publication / restore label (optional)", { exact: true })
        .fill("Synthetic publication");
      await page
        .getByRole("button", {
          name: "Publish complete course draft",
          exact: true,
        })
        .click();
      await expect(page.getByText(/Course version 3 published/)).toBeVisible();
      await page
        .getByRole("button", { name: "Browse & compare", exact: true })
        .first()
        .click();
      await expect(page.locator(".diff-card h4")).toContainText("Questions");
      await expect(page.locator(".diff-columns")).toContainText(
        "Original synthetic question",
      );
      await page
        .getByRole("button", { name: "Restore as new edition", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Confirm restore", exact: true })
        .click();
      await expect(page.getByText(/Course version 4 published/)).toBeVisible();
      expect(editions.map((v) => v.number)).toEqual([1, 2, 3, 4]);
      expect(operational.starts_at).not.toBeNull();
      await page.screenshot({
        path: path.join(artifacts, "versions-desktop.png"),
        fullPage: true,
      });
    },
  );
  await page
    .locator(".tabs")
    .getByRole("button", { name: "Course roster", exact: true })
    .click();
  await check(
    "Roster import preview/commit omits password from visible review",
    async () => {
      await page.getByText("Import CSV / XLSX roster", { exact: true }).click();
      await page.getByLabel("Choose a file", { exact: true }).setInputFiles({
        name: "synthetic.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          "name,email,temporary_password\nSynthetic Import,import@example.invalid,Synthetic123\n",
        ),
      });
      await page
        .getByRole("button", { name: "Validate and preview", exact: true })
        .click();
      await expect(
        page.getByText("Synthetic warning only", { exact: true }),
      ).toBeVisible();
      expect(await page.locator("body").innerText()).not.toContain(
        "Synthetic123",
      );
      await page
        .getByRole("button", { name: "Commit reviewed import", exact: true })
        .click();
      await expect(
        page.getByText("import@example.invalid", { exact: true }),
      ).toBeVisible();
    },
  );
  await check(
    "Course archive blocks navigation until verified, retains records and countdown; restore cancels deadline",
    async () => {
      await page
        .getByRole("checkbox", { name: "student@example.invalid", exact: true })
        .check();
      await page
        .getByRole("button", { name: "Archive selected (1)", exact: true })
        .click();
      let releaseArchive;
      rosterActionGate = new Promise((resolve) => { releaseArchive = resolve; });
      await page
        .locator(".confirmation")
        .getByRole("button", { name: "Confirm archive", exact: true })
        .click();
      try {
        await expect(page.getByRole("button", { name: "Recycle bin", exact: true })).toBeDisabled();
        await expect(page.getByRole("button", { name: "Refresh status", exact: true })).toBeDisabled();
      } finally {
        releaseArchive();
        rosterActionGate = null;
      }
      await page
        .getByRole("button", { name: "Recycle bin", exact: true })
        .click();
      await expect(page.locator(".retention-countdown")).toContainText("30d");
      await page
        .getByRole("checkbox", { name: "student@example.invalid", exact: true })
        .check();
      await page
        .getByRole("button", { name: "Restore selected (1)", exact: true })
        .click();
      await page
        .locator(".confirmation")
        .getByRole("button", { name: "Confirm restore", exact: true })
        .click();
      await expect(
        page.getByText("No students in this list", { exact: true }),
      ).toBeVisible();
      expect(roster[0].purge_at).toBeNull();
      await page.screenshot({
        path: path.join(artifacts, "roster-desktop.png"),
        fullPage: true,
      });
    },
  );
  await page
    .locator(".tabs")
    .getByRole("button", { name: "Learning records", exact: true })
    .click();
  await check(
    "Teacher observation pins historical edition and is not a draft sandbox",
    async () => {
      await page
        .getByLabel("Content edition", { exact: true })
        .selectOption("v1");
      await page
        .getByRole("button", { name: "View record", exact: true })
        .click();
      await expect(page.locator(".composer")).toHaveCount(0);
      await expect(
        page.getByText("Read-only student record", { exact: true }).first(),
      ).toBeVisible();
      expect(page.url()).toContain("version_id=v1");
    },
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("button", { name: "Try as admin", exact: true }).click();
  await check(
    "Admin-only global settings and authorized teacher promotion",
    async () => {
      await page
        .getByRole("button", { name: "Model settings", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "A clear view of your AI connection.",
          exact: true,
        }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Account administration", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Promote to admin", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Confirm promotion", exact: true })
        .click();
      await expect(
        page.getByText("Teacher promoted to administrator.", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", {
          name: "Global student accounts",
          exact: true,
        }),
      ).toBeVisible();
    },
  );
  await check(
    "Demo profile disables password editing and remains English-only after reload",
    async () => {
      await page
        .getByRole("button", { name: "User Profile", exact: true })
        .click();
      await expect(
        page.getByText("Synthetic demo accounts cannot change passwords.", {
          exact: true,
        }),
      ).toBeVisible();
      await englishOnly();
      await page.reload();
      await expect(
        page.getByRole("heading", { name: "User Profile", exact: true }),
      ).toBeVisible();
      await englishOnly();
    },
  );
  await check(
    "Responsive management and workspace avoid horizontal overflow",
    async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("http://127.0.0.1:18778/#/teacher/s1");
      await expect(
        page.getByRole("heading", { name: "Synthetic classroom", exact: true }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: path.join(artifacts, "teacher-mobile.png"),
        fullPage: true,
      });
      await page
        .getByRole("button", { name: "Draft learning preview", exact: true })
        .click();
      await expect(
        page.getByRole("textbox", {
          name: "Answer this question",
          exact: true,
        }),
      ).toHaveValue("");
      await page.getByRole("button", { name: /Worksheet ·/ }).click();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: path.join(artifacts, "workspace-mobile.png"),
        fullPage: true,
      });
    },
  );
  expect(errors).toEqual([]);
  const result = {
    scope:
      "EXPLICIT SYNTHETIC FRONTEND HTTP FIXTURES; NOT BACKEND OR REAL-MODEL EVIDENCE",
    passed: checks.length,
    checks,
    page_errors: errors,
    request_count: calls.length,
  };
  await fs.writeFile(
    path.join(artifacts, "result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
} catch (e) {
  console.error("Completed fixture checks:", checks);
  throw e;
} finally {
  await browser?.close();
  await server.close();
}
