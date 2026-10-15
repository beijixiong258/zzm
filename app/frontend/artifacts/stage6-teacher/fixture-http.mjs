// Labelled UI-only HTTP fixtures: never evidence of backend/model correctness.
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
const clone = (x) => structuredClone(x);
const stamp = "2026-10-07T00:00:00Z";
export const report = {
  schema_version: 1,
  method: "synthetic-native-text",
  units_total: 2,
  units_processed: 1,
  ocr_units: 1,
  images_detected: 1,
  chars_extracted: 33,
  excerpt_chars: 33,
  truncated: false,
  visual_review_required: true,
  failed_units: ["Fixture second page not extracted"],
  notes: ["Explicit synthetic extraction coverage"],
};
const profile = {
  schema_version: 1,
  background: "Synthetic postgraduate course.",
  student_profile: "Teaching experience.",
  response_strategies: "Ask for a reason before comparison.",
  tone: "Supportive and specific.",
  response_detail: "balanced",
  phases: ["worksheet", "quiz", "wrap_up"],
  reading_focus: "",
  reading_question_count: 3,
  reference_delivery: "on_request",
  idle_hint_seconds: 0,
  presentation: "full",
};
const material = (id, visibility = "student", kind = "reading") => ({
  id,
  title: "Duplicate source label",
  kind,
  visibility,
  source_label: "Duplicate source label",
  status: "ready",
  excerpt: `Exact evidence from ${id}.\nKeep spacing.`,
  extraction_report: clone(report),
});
function session(id) {
  return {
    id,
    course_id: "fixture-course",
    title: `Teaching design ${id}`,
    subtitle: "Synthetic teacher workbench",
    number: id.endsWith("1") ? 1 : 2,
    status: "published",
    question_count: 2,
    estimated_minutes: 20,
    learning_objectives: ["Explain source evidence."],
    instructions: "Saved synthetic instruction.",
    reference_policy: "after_attempt",
    teaching_language: "en",
    active: true,
    effective_active: true,
    availability_reason: "manual_active",
    starts_at: null,
    ends_at: null,
    teaching_profile: clone(profile),
    groups: [{ id: "core", title: "Required worksheet", kind: "core" }],
    questions: [1, 2].map((n) => ({
      id: `q${n}`,
      group_id: "core",
      ordinal: n,
      type: "open_response",
      prompt: `Explain synthetic concept ${n}.`,
      options: n === 1 ? ["First response", "Second response"] : [],
      answer_slots: 1,
      images: [],
      source_label: "Synthetic worksheet",
      source_material_ids: ["public-a", "public-b"],
    })),
    reference_answers: {
      q1: "Exact private reference.\n  Preserve indentation.",
      q2: "Second instructor reference.",
    },
    materials: [
      material("public-a"),
      material("public-b"),
      material("private-k", "teacher"),
      material("private-key", "teacher", "answer_key"),
      material("unselected"),
    ],
  };
}
export function fixtures() {
  const sessions = new Map(
    ["fixture-s1", "fixture-s2"].map((id) => [id, session(id)]),
  );
  const runs = new Map(),
    logs = [],
    control = {
      turnFail: 0,
      turnDelay: 0,
      sourceDelay: 0,
      importDelay: 0,
      sessionDelay: 0,
      workspaceDelay: 0,
      completedWrong: false,
    };
  let serial = 0;
  const revision = (s) =>
    `fixture-revision-${JSON.stringify([s.title, s.subtitle, s.instructions, s.teaching_profile, s.learning_objectives, s.questions, s.materials]).length}-${s.instructions.slice(-8)}`;
  const run = (id) => {
    if (!runs.has(id))
      runs.set(id, {
        id: null,
        revision: null,
        messages: [],
        attempts: {},
        tutor: {
          phase: "not_started",
          started_at: null,
          updated_at: null,
          elapsed_seconds: 0,
          current_question_id: null,
          completed_question_ids: [],
          question_states: {},
          quiz: { status: "not_offered", answered: 0, total: 5, correct: null },
          reading: { answered: 0, total: 0 },
          presentation: "full",
          idle_hint_seconds: 0,
          pending_request_id: null,
          last_completed_request_id: null,
        },
      });
    return runs.get(id);
  };
  const preview = (id) => {
    const r = run(id),
      current = revision(sessions.get(id)),
      stale = !!r.id && r.revision !== current;
    return {
      id: r.id,
      revision: r.revision,
      current_revision: current,
      stale,
      reset_required: stale,
      pending: !!r.tutor.pending_request_id,
      bound_at: r.id ? stamp : null,
    };
  };
  const workspace = (id) => {
    const r = run(id),
      p = preview(id);
    return {
      session: clone(sessions.get(id)),
      user: {
        id: "fixture-teacher",
        name: "Fixture teacher",
        email: "fixture@example.invalid",
        role: "teacher",
      },
      version: { id: null, number: null, is_current: false, is_draft: true },
      available_versions: [],
      selected_reading: null,
      attempts: clone(r.attempts),
      messages: clone(r.messages),
      progress: {
        answered: 0,
        total: 2,
        active_question_ids: ["q1", "q2"],
        current_question_id: r.tutor.current_question_id,
      },
      submission: {
        status: "in_progress",
        submitted_at: null,
        reviewed_at: null,
        teacher_note: "",
      },
      ai: {
        mode: "demo",
        configured: true,
        base_url: "",
        model: "labelled-http-fixture",
        web_search: { enabled: false, configured: false, provider: "tavily" },
      },
      tutor: clone(r.tutor),
      preview: p,
      read_only: p.stale,
      read_only_reason: p.stale ? "preview_stale" : null,
    };
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function api(req, res) {
    const url = new URL(req.url, "http://127.0.0.1");
    const bytes = Buffer.concat(await Array.fromAsync(req));
    const body =
      bytes.length &&
      !(req.headers["content-type"] || "").startsWith("multipart")
        ? JSON.parse(bytes.toString())
        : {};
    logs.push({
      method: req.method,
      path: url.pathname,
      body: clone(body),
      multipart: (req.headers["content-type"] || "").startsWith("multipart"),
      bytes: bytes.length,
    });
    const send = (data, status = 200) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(data));
    };
    const match = url.pathname.match(
      /^\/api\/(?:teacher\/)?sessions\/(fixture-s[12])(?:\/(.*))?$/,
    );
    if (!match) return send({ detail: "Unknown UI fixture endpoint" }, 404);
    const [, id, tail = ""] = match,
      s = sessions.get(id),
      r = run(id);
    if (!tail && req.method === "GET") {
      const snapshot = clone(s);
      await sleep(control.sessionDelay);
      return send(snapshot);
    }
    if (!tail && req.method === "PATCH") {
      Object.assign(s, body);
      return send(s);
    }
    if (tail === "workspace") {
      const snapshot = workspace(id);
      await sleep(control.workspaceDelay);
      return send(snapshot);
    }
    if (tail === "preview") return send(preview(id));
    if (tail === "preview/reset") {
      if (r.tutor.pending_request_id)
        return send({ detail: "Preview inference is pending" }, 409);
      if (body.expected_revision !== preview(id).current_revision)
        return send({ detail: "Saved draft revision changed" }, 409);
      runs.delete(id);
      const fresh = run(id);
      fresh.id = `fixture-preview-${++serial}`;
      fresh.revision = revision(s);
      return send(workspace(id));
    }
    if (tail === "tutor/start" || tail === "tutor/turn") {
      if (body.preview_id !== r.id || preview(id).stale)
        return send({ detail: "Preview is stale or replaced" }, 409);
      if (tail === "tutor/start") {
        r.tutor.phase = "worksheet";
        r.tutor.current_question_id = "q1";
        r.tutor.started_at = stamp;
        r.tutor.last_completed_request_id = body.request_id;
        r.messages.push({
          id: `message-${++serial}`,
          role: "assistant",
          content: "Synthetic fixture guide. Explain your reasoning.",
          question_id: "q1",
          presented_question_id: "q1",
          created_at: stamp,
          mode: "demo",
          metadata: { phase: "worksheet" },
        });
        return send(workspace(id));
      }
      r.tutor.pending_request_id = body.request_id;
      await sleep(control.turnDelay);
      r.tutor.pending_request_id = null;
      if (control.turnFail > 0) {
        control.turnFail--;
        if (control.completedWrong)
          r.tutor.last_completed_request_id = "some-other-request";
        return send(
          {
            detail:
              "Deliberate HTTP fixture failure; retry identity must survive",
          },
          503,
        );
      }
      r.messages.push(
        {
          id: `message-${++serial}`,
          role: "user",
          content: body.message,
          question_id: "q1",
          created_at: stamp,
          mode: "demo",
        },
        {
          id: `message-${++serial}`,
          role: "assistant",
          content: "Synthetic accepted response — no model inference.",
          question_id: "q1",
          created_at: stamp,
          mode: "demo",
          metadata: { phase: "worksheet" },
        },
      );
      r.tutor.last_completed_request_id = body.request_id;
      return send(workspace(id));
    }
    if (tail === "teaching-preview")
      return send({
        text: `Synthetic compiled instructions\n${body.instructions}`,
        sections: [
          {
            id: "additional",
            title: "Additional instructions",
            text: body.instructions,
          },
        ],
        warnings: [],
      });
    if (tail === "source-review") {
      const overlay = Object.hasOwn(body, "instructions"),
        optional = ["quiz", "reading"].includes(body.phase);
      const selected = s.materials.filter(
        (m) => !m.id.startsWith("unselected"),
      );
      const publicItems = selected.filter((m) => m.visibility === "student");
      const privateItems = optional
        ? []
        : selected.filter((m) => m.id === "private-k");
      const data = {
        scope: overlay ? "unsaved_instruction_overlay" : "saved_draft",
        saved_revision: revision(s),
        question_id: body.question_id,
        phase: body.phase,
        compiled: {
          text: `Exact synthetic compilation\n${overlay ? body.instructions : s.instructions}`,
          sections: [],
          warnings: [],
        },
        public_evidence: publicItems.map((m) => ({
          material_id: m.id,
          source_label: m.source_label,
          excerpt: m.excerpt,
        })),
        private_evidence: privateItems.map((m) => ({
          material_id: m.id,
          source_label: m.source_label,
          excerpt: m.excerpt,
        })),
        private_reference:
          !optional && body.question_id
            ? {
                question_id: body.question_id,
                text: s.reference_answers[body.question_id],
                eligibility: s.reference_policy,
                delivery: s.teaching_profile.reference_delivery,
              }
            : null,
        materials: s.materials.map((m) => ({
          id: m.id,
          title: m.title,
          kind: m.kind,
          visibility: m.visibility,
          status: m.status,
          role:
            m.id === "private-key"
              ? "answer_key"
              : m.visibility === "teacher"
                ? "private_knowledge"
                : "public_knowledge",
          selected: m.id !== "unselected",
          included: publicItems.concat(privateItems).some((p) => p.id === m.id),
          available_chars: m.excerpt.length,
          included_chars: publicItems
            .concat(privateItems)
            .some((p) => p.id === m.id)
            ? m.excerpt.length
            : 0,
          reason:
            m.id === "unselected"
              ? "not selected"
              : m.id === "private-key"
                ? "answer key excluded"
                : optional && m.visibility === "teacher"
                  ? "optional phase excludes private material"
                  : "selected bounded evidence",
          extraction_report: clone(report),
        })),
        warnings: ["Synthetic coverage warning: some pages need review."],
        budgets: {
          public_chars: publicItems.reduce((a, m) => a + m.excerpt.length, 0),
          private_chars: privateItems.reduce((a, m) => a + m.excerpt.length, 0),
          request_bytes: 1024,
        },
      };
      await sleep(control.sourceDelay);
      return send(data);
    }
    if (tail === "instruction-import/preview") {
      if (
        !(req.headers["content-type"] || "").startsWith(
          "multipart/form-data; boundary=",
        )
      )
        return send({ detail: "Real multipart upload required" }, 400);
      const raw = bytes.toString(),
        filename = raw.match(/filename="([^"]+)"/)?.[1] || "unknown.txt";
      const uploaded = raw.split("\r\n\r\n")[1]?.split("\r\n--")[0] || "";
      await sleep(control.importDelay);
      if (filename.startsWith("error"))
        return send({ detail: "Deliberate parser HTTP failure" }, 422);
      return send({
        filename,
        text: uploaded,
        status: "needs_review",
        warning:
          "Labelled synthetic extraction response: OCR/partial review required.",
        extraction_report: {
          ...clone(report),
          chars_extracted: uploaded.length,
          excerpt_chars: uploaded.length,
        },
        max_instruction_chars: 30000,
      });
    }
    return send({ detail: "Out of labelled UI fixture scope" }, 404);
  }
  return {
    logs,
    control,
    sessions,
    workspace,
    handler: api,
    snapshot: () => ({
      sessions: Array.from(sessions),
      runs: Array.from(runs),
      logs: clone(logs),
    }),
  };
}
export async function serveFixture(buildDir) {
  const fixture = fixtures();
  const server = http.createServer(async (req, res) => {
    try {
      if (req.url.startsWith("/api/")) return await fixture.handler(req, res);
      const requestPath = new URL(req.url, "http://127.0.0.1").pathname;
      const filename = path.resolve(
        buildDir,
        `.${requestPath === "/" ? "/artifacts/stage6-teacher/index.html" : requestPath}`,
      );
      if (!filename.startsWith(path.resolve(buildDir) + path.sep)) {
        res.writeHead(403);
        res.end();
        return;
      }
      const content = await fs.readFile(filename),
        ext = path.extname(filename);
      res.writeHead(200, {
        "Content-Type":
          {
            ".html": "text/html",
            ".js": "text/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
          }[ext] || "application/octet-stream",
      });
      res.end(content);
    } catch (e) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: String(e) }));
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { fixture, server, url: `http://127.0.0.1:${server.address().port}` };
}
