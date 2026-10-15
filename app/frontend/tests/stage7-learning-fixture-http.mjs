// Synthetic HTTP state only. No backend imports or provider clients.
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const seed = JSON.parse(
  await fs.readFile(
    new URL("./stage7-learning-fixture.json", import.meta.url),
    "utf8",
  ),
);
const clone = (value) => structuredClone(value);
export async function serveLearningFixture(built) {
  const fixture = {
    data: clone(seed),
    logs: [],
    failures: 0,
    libraryError: false,
    turns: new Map(),
  };
  const json = (res, value, status = 200) => {
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(value));
  };
  const text = (res, value, type = "text/plain", headers = {}) => {
    res.writeHead(200, { "Content-Type": type, ...headers });
    res.end(value);
  };
  const server = http.createServer(async (req, res) => {
    try {
      const u = new URL(req.url, "http://127.0.0.1");
      const route = u.pathname;
      const method = req.method;
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const raw = Buffer.concat(chunks).toString();
      const body =
        req.headers["content-type"]?.includes("application/json") && raw
          ? JSON.parse(raw)
          : {};
      const d = fixture.data;
      if (route.startsWith("/api/"))
        fixture.logs.push({ method, path: route, query: u.search, body });
      if (route === "/api/courses") return json(res, [d.course]);
      if (route === "/api/courses/fixture-course/sessions")
        return json(res, d.sessions);
      if (route === "/api/courses/fixture-course/materials")
        return fixture.libraryError
          ? json(
              res,
              {
                detail:
                  "Fixture permission failure: only this course's owner may manage its library.",
              },
              403,
            )
          : json(res, { materials: d.materials });
      if (route === "/api/history") return json(res, d.history);
      if (/\/teacher\/sessions\/[^/]+\/students\/[^/]+\/workspace$/.test(route))
        return json(res, d.record);
      if (/\/workspace$/.test(route)) return json(res, d.workspace);
      if (/\/tutor\/turn$/.test(route)) {
        const w = d.workspace;
        if (!fixture.turns.has(body.request_id)) {
          fixture.turns.set(body.request_id, body.message);
          w.messages.push({
            id: `fixture-user-${fixture.turns.size}`,
            role: "user",
            content: body.message,
            question_id: "fixture-question",
            mode: "openai",
            intent: "answer",
            created_at: "2026-10-07T12:01:00Z",
          });
        }
        if (fixture.failures > 0) {
          fixture.failures--;
          return json(
            res,
            {
              detail:
                "Fixture provider unavailable. Your response was saved; retry the same request.",
            },
            503,
          );
        }
        w.tutor.last_completed_request_id = body.request_id;
        return json(res, w);
      }
      if (/\/answers\/fixture-question$/.test(route)) {
        const w = d.workspace;
        const attempt = w.attempts["fixture-question"];
        attempt.answer = body.answer;
        attempt.revision_count++;
        attempt.revisions.push({
          answer: body.answer,
          created_at: "2026-10-07T12:02:00Z",
        });
        return json(res, w);
      }
      if (/\/references\/fixture-question$/.test(route)) {
        if (d.workspace.submission.status !== "submitted")
          return json(
            res,
            {
              detail:
                "Submit your work before requesting the instructor example.",
            },
            409,
          );
        d.workspace.attempts["fixture-question"].reference_revealed = true;
        return json(res, {
          reference:
            "Synthetic comparison: relate evidence to purpose and consequences.",
          source_label: "Labelled fixture instructor example",
        });
      }
      if (/\/submit$/.test(route)) {
        d.workspace.submission.status = "submitted";
        return json(res, d.workspace);
      }
      const sessionId = route.match(/^\/api\/sessions\/([^/]+)/)?.[1];
      const session = d.sessions.find((s) => s.id === sessionId);
      if (session && route === `/api/sessions/${sessionId}`)
        return json(res, session);
      if (session && /\/materials\/attach$/.test(route)) {
        const material = d.materials.find((m) => m.id === body.material_id);
        if (!material.session_ids.includes(sessionId))
          material.session_ids.push(sessionId);
        session.materials = d.materials.filter((m) =>
          m.session_ids.includes(sessionId),
        );
        return json(res, material);
      }
      if (session && /\/materials\/link$/.test(route)) {
        const m = {
          id: "fixture-link",
          title: body.title || "Fixture link",
          kind: "link",
          visibility: body.visibility,
          source_label: "Synthetic saved link",
          status: "ready",
          excerpt: "Fixture link text",
          url: body.url,
          session_ids: [sessionId],
          preview_kind: "link",
        };
        d.materials.push(m);
        session.materials.push(m);
        return json(res, m);
      }
      const mid = route.match(/\/materials\/([^/]+)$/)?.[1];
      if (session && mid && method === "DELETE") {
        const m = d.materials.find((x) => x.id === mid);
        m.session_ids = m.session_ids.filter((id) => id !== sessionId);
        session.materials = session.materials.filter((x) => x.id !== mid);
        return json(res, { ok: true });
      }
      if (session && mid && method === "PATCH") {
        const m = d.materials.find((x) => x.id === mid);
        Object.assign(m, body);
        return json(res, m);
      }
      if (/\/worksheet-import\/preview$/.test(route)) {
        return json(res, {
          import_id: "fixture-import",
          material: d.materials[0],
          method: "Synthetic local fixture extraction",
          needs_review: true,
          assets: [],
          warnings: [
            "Fixture extraction requires review; no document or model was processed.",
          ],
          draft: {
            title: "Synthetic imported worksheet",
            groups: session.groups,
            questions: [
              {
                ...session.questions[0],
                id: "fixture-imported-question",
                ordinal: 2,
              },
            ],
            reference_answers: {},
          },
        });
      }
      if (/\/worksheet-import\/fixture-import\/commit$/.test(route)) {
        session.groups = body.groups;
        session.questions =
          body.mode === "replace"
            ? body.questions
            : [...session.questions, ...body.questions];
        return json(res, session);
      }
      if (/\/materials\/[^/]+\/preview$/.test(route))
        return text(
          res,
          "Synthetic authenticated original material text.\nNot live course content.",
        );
      if (/\/materials\/[^/]+\/download$/.test(route))
        return text(
          res,
          "Synthetic authenticated original material text.\nNot live course content.",
          "text/plain",
          {
            "Content-Disposition":
              'attachment; filename="fixture-material.txt"',
          },
        );
      if (/\/transcript$/.test(route))
        return text(
          res,
          d.workspace.messages.map((m) => m.content).join("\n\n"),
          "text/plain",
          {
            "Content-Disposition":
              'attachment; filename="fixture-transcript.txt"',
          },
        );
      if (/\/export$/.test(route))
        return text(res, JSON.stringify(d.record), "application/json", {
          "Content-Disposition": 'attachment; filename="fixture-record.json"',
        });
      if (route.startsWith("/api/"))
        return json(
          res,
          { detail: `Unimplemented fixture endpoint ${method} ${route}` },
          404,
        );
      const target =
        route === "/" ? "tests/stage7-learning-harness.html" : route.slice(1);
      const file = path.resolve(built, target);
      if (!file.startsWith(path.resolve(built) + path.sep))
        return json(res, { detail: "Outside fixture build" }, 403);
      const bytes = await fs.readFile(file);
      const ext = path.extname(file);
      res.writeHead(200, {
        "Content-Type":
          {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
            ".png": "image/png",
          }[ext] || "application/octet-stream",
      });
      res.end(bytes);
    } catch (e) {
      json(res, { detail: String(e) }, 500);
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  return { fixture, server, url, source: fileURLToPath(import.meta.url) };
}
