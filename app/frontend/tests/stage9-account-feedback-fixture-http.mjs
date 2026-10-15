// Synthetic HTTP protocol state only. No FastAPI, SQLite, image normalization or auth claim.
export function stage9Fixture() {
  const users = {
    "student-a": {
      id: "student-a",
      name: "Synthetic Student A",
      email: "student-a@example.invalid",
      role: "student",
      avatar_url: null,
    },
    "student-b": {
      id: "student-b",
      name: "Synthetic Student B",
      email: "student-b@example.invalid",
      role: "student",
      avatar_url: null,
    },
    admin: {
      id: "admin",
      name: "Synthetic Administrator",
      email: "admin@example.invalid",
      role: "admin",
      avatar_url: null,
    },
  };
  let account = "student-a",
    serial = 0,
    normalized = Buffer.alloc(0);
  const counts = {
    upload: 0,
    remove: 0,
    me: 0,
    image: 0,
    profile: 0,
    password: 0,
    create: 0,
    request: 0,
    detail: 0,
    list: 0,
    update: 0,
  };
  const controls = {
    failWrite: false,
    failMe: 0,
    staleMe: null,
    failImage: false,
    meAfterAvatar: 0,
    staleAfterAvatar: false,
    failList: 0,
    failDetail: 0,
    detailAfterCreate: 0,
    detailAfterUpdate: 0,
    failCreate: 0,
    unknownCreate: false,
    failRequest: 0,
    unknownUpdate: false,
    failUpdate: false,
  };
  const rows = [];
  const seed = (id, author, subject, index) => ({
    id,
    author_id: author,
    request_id: "request-" + id,
    category: index % 2 ? "bug" : "general",
    subject,
    message: "Synthetic literal message\nSecond line",
    status: index % 4 ? "new" : "reviewed",
    reply: index % 4 ? "" : "Synthetic prior reply",
    created_at: new Date(Date.UTC(2026, 0, 1, 0, 0, index)).toISOString(),
    updated_at: new Date(Date.UTC(2026, 0, 1, 0, 0, index)).toISOString(),
    revision: 1,
  });
  for (let i = 1; i <= 31; i++)
    rows.push(seed("a-" + i, "student-a", "Student A feedback " + i, i));
  rows.push(
    seed("b-1", "student-b", "Student B private feedback", 40),
    seed("b-2", "student-b", "Student B second feedback", 41),
    seed("admin-1", "admin", "Administrator own feedback", 42),
  );
  const createRequests = [];
  const holds = new Map();
  function hold(id) {
    let release, entered;
    const enteredPromise = new Promise((r) => (entered = r)),
      wait = new Promise((r) => (release = r));
    holds.set(id, { wait, entered });
    return {
      entered: enteredPromise,
      release: () => {
        holds.delete(id);
        release();
      },
    };
  }
  const projection = (row) => ({
    ...row,
    author: row.author_id
      ? {
          id: users[row.author_id].id,
          name: users[row.author_id].name,
          email: users[row.author_id].email,
          role: users[row.author_id].role,
        }
      : null,
  });
  const send = (res, status, data) => {
    res.writeHead(status, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    res.end(JSON.stringify(data));
  };
  const plugin = {
    name: "stage9-account-feedback-http-fixture",
    configureServer(s) {
      s.middlewares.use(async (req, res, next) => {
        const u = new URL(req.url, "http://127.0.0.1"),
          p = u.pathname,
          m = req.method;
        if (p.startsWith("/fixture/account/")) {
          account = p.split("/").at(-1);
          return send(res, 200, { ok: true });
        }
        if (!p.startsWith("/api/")) return next();
        try {
          const bytes = [];
          for await (const chunk of req) bytes.push(chunk);
          const body = Buffer.concat(bytes);
          const data =
            body.length && (req.headers["content-type"] || "").includes("json")
              ? JSON.parse(body.toString())
              : {};
          if (p === "/api/auth/me") {
            counts.me++;
            if (controls.failMe) {
              controls.failMe--;
              return send(res, 503, {
                detail: "Synthetic account readback unavailable",
              });
            }
            if (controls.staleMe) {
              const stale = controls.staleMe;
              controls.staleMe = null;
              return send(res, 200, { user: stale });
            }
            return send(res, 200, { user: users[account] });
          }
          if (p === "/api/auth/profile") {
            counts.profile++;
            users[account].name = data.name;
            return send(res, 200, { user: users[account] });
          }
          if (p === "/api/auth/change-password") {
            counts.password++;
            return send(res, 200, { user: users[account] });
          }
          if (p === "/api/auth/avatar") {
            const action = m === "DELETE" ? "remove" : "upload";
            counts[action]++;
            if (controls.failWrite) {
              controls.failWrite = false;
              return send(res, 422, {
                detail: "Synthetic avatar write rejected",
              });
            }
            const old = { ...users[account] };
            users[account].avatar_url =
              action === "remove"
                ? null
                : `/api/users/${account}/avatar?v=synthetic-${++serial}`;
            if (controls.meAfterAvatar) {
              controls.failMe = controls.meAfterAvatar;
              controls.meAfterAvatar = 0;
            }
            if (controls.staleAfterAvatar) {
              controls.staleMe = old;
              controls.staleAfterAvatar = false;
            }
            return send(res, 200, { user: users[account] });
          }
          if (/^\/api\/users\/[^/]+\/avatar$/.test(p)) {
            counts.image++;
            const id = p.split("/")[3];
            if (controls.failImage)
              return send(res, 503, { detail: "Synthetic image failure" });
            if (!users[id] || users[id].avatar_url !== p + u.search)
              return send(res, 404, { detail: "Avatar not found" });
            res.writeHead(200, {
              "Content-Type": "image/png",
              "Cache-Control": "no-store",
            });
            res.end(normalized);
            return;
          }
          const isAdmin = p.startsWith("/api/admin/feedback"),
            prefix = isAdmin ? "/api/admin/feedback" : "/api/feedback";
          if (isAdmin && users[account].role !== "admin")
            return send(res, 403, { detail: "Admin required" });
          if (p === prefix && m === "GET") {
            counts.list++;
            if (controls.failList) {
              controls.failList--;
              return send(res, 503, { detail: "Synthetic list unavailable" });
            }
            const offset = Number(u.searchParams.get("offset") || 0),
              limit = Number(u.searchParams.get("limit") || 25);
            const filtered = rows
              .filter(
                (row) =>
                  (isAdmin || row.author_id === account) &&
                  (!u.searchParams.get("status") ||
                    row.status === u.searchParams.get("status")) &&
                  (!u.searchParams.get("category") ||
                    row.category === u.searchParams.get("category")),
              )
              .sort(
                (a, b) =>
                  b.created_at.localeCompare(a.created_at) ||
                  b.id.localeCompare(a.id),
              );
            return send(res, 200, {
              items: filtered.slice(offset, offset + limit).map(projection),
              total: filtered.length,
              offset,
              limit,
            });
          }
          if (p === "/api/feedback" && m === "POST") {
            counts.create++;
            createRequests.push({ ...data });
            if (controls.failCreate) {
              const status = controls.failCreate;
              controls.failCreate = 0;
              return send(res, status, {
                detail: "Synthetic submission rejected",
              });
            }
            const normalizedData = {
              ...data,
              subject: data.subject.trim(),
              message: data.message.trim(),
            };
            let row = rows.find(
              (r) =>
                r.author_id === account && r.request_id === data.request_id,
            );
            if (row) {
              if (
                ["category", "subject", "message"].some(
                  (key) => row[key] !== normalizedData[key],
                )
              )
                return send(res, 409, {
                  detail: "Request ID already used for a different payload",
                });
            } else {
              const now = new Date().toISOString();
              row = {
                ...normalizedData,
                id: "created-" + ++serial,
                author_id: account,
                status: "new",
                reply: "",
                created_at: now,
                updated_at: now,
                revision: 1,
              };
              rows.push(row);
            }
            if (controls.detailAfterCreate) {
              controls.failDetail = controls.detailAfterCreate;
              controls.detailAfterCreate = 0;
            }
            if (controls.unknownCreate) {
              controls.unknownCreate = false;
              return send(res, 503, {
                detail: "Synthetic lost POST response after commit",
              });
            }
            return send(res, 200, projection(row));
          }
          if (p.startsWith("/api/feedback/requests/")) {
            counts.request++;
            if (controls.failRequest) {
              controls.failRequest--;
              return send(res, 503, {
                detail: "Synthetic request recovery unavailable",
              });
            }
            const id = decodeURIComponent(
                p.slice("/api/feedback/requests/".length),
              ),
              row = rows.find(
                (r) => r.author_id === account && r.request_id === id,
              );
            return row
              ? send(res, 200, projection(row))
              : send(res, 404, { detail: "Request not found" });
          }
          if (p.startsWith(prefix + "/")) {
            const id = decodeURIComponent(p.slice(prefix.length + 1)),
              row = rows.find(
                (r) => r.id === id && (isAdmin || r.author_id === account),
              );
            if (!row) return send(res, 404, { detail: "Feedback not found" });
            if (m === "GET") {
              counts.detail++;
              const snapshot = projection({ ...row }),
                barrier = holds.get(id);
              if (barrier) {
                barrier.entered();
                await barrier.wait;
              }
              if (controls.failDetail) {
                controls.failDetail--;
                return send(res, 503, {
                  detail: "Synthetic feedback readback unavailable",
                });
              }
              return send(res, 200, snapshot);
            }
            if (m === "PATCH" && isAdmin) {
              counts.update++;
              if (controls.failUpdate) {
                controls.failUpdate = false;
                return send(res, 422, { detail: "Synthetic reply rejected" });
              }
              if (data.expected_revision !== row.revision)
                return send(res, 409, {
                  detail: "Feedback changed. Reload the latest revision.",
                });
              Object.assign(row, {
                status: data.status,
                reply: data.reply.trim(),
                revision: row.revision + 1,
                updated_at: new Date().toISOString(),
              });
              if (controls.detailAfterUpdate) {
                controls.failDetail = controls.detailAfterUpdate;
                controls.detailAfterUpdate = 0;
              }
              if (controls.unknownUpdate) {
                controls.unknownUpdate = false;
                return send(res, 503, {
                  detail: "Synthetic lost PATCH response after commit",
                });
              }
              return send(res, 200, projection(row));
            }
          }
          return send(res, 404, { detail: "Unknown fixture endpoint" });
        } catch (e) {
          return send(res, 500, { detail: String(e) });
        }
      });
    },
  };
  return {
    plugin,
    users,
    rows,
    counts,
    controls,
    createRequests,
    hold,
    setImage: (bytes) => {
      normalized = bytes;
    },
    current: () => account,
  };
}
