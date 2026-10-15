// Synthetic HTTP DTO fixture. No backend authentication, import parsing or DB claims.
export function personnelFixture() {
  const accounts = new Map(),
    imports = new Map(),
    staff = new Map([
      ["c1", ["admin", "teacher-a", "teacher-b"]],
      ["c2", ["other-admin", "teacher-a"]],
      ["c3", ["other-admin"]],
    ]),
    owners = new Map([
      ["c1", "admin"],
      ["c2", "other-admin"],
      ["c3", "other-admin"],
    ]);
  const courses = [
    {
      id: "c1",
      code: "SYN101",
      title: "Synthetic Course One",
      trashed_at: null,
    },
    {
      id: "c2",
      code: "SYN202",
      title: "Synthetic Course Two",
      trashed_at: null,
    },
    {
      id: "c3",
      code: "SYN303",
      title: "Unassigned Course",
      trashed_at: "2026-01-01T00:00:00Z",
    },
  ];
  let serial = 0,
    registration = true;
  function seed(id, name, role) {
    accounts.set(id, {
      user: {
        id,
        name,
        email: id + "@example.invalid",
        role,
        must_change_password: false,
        avatar_url: null,
      },
      active: true,
      archived_at: null,
      purge_at: null,
    });
  }
  seed("admin", "Synthetic Admin", "admin");
  seed("other-admin", "Other Admin", "admin");
  seed("teacher-a", "Synthetic Teacher A", "teacher");
  seed("teacher-b", "Synthetic Teacher B", "teacher");
  seed("student-a", "Synthetic Student A", "student");
  seed("existing", "Existing Student", "student");
  for (let i = 0; i < 12; i++)
    seed("student-" + i, "Student " + String(i).padStart(2, "0"), "student");
  const enrollments = new Map([
    ["c1", new Map([["student-a", false]])],
    ["c2", new Map([["student-a", false]])],
    ["c3", new Map()],
  ]);
  const controls = {
    failGet: 0,
    afterWriteReadFailure: false,
    unknownCreate: false,
    unknownCommit: false,
    roleConflict: "",
    staffConflict: "",
    previewError: false,
  };
  const counts = {
    create: 0,
    role: 0,
    status: 0,
    preview: 0,
    commit: 0,
    importGet: 0,
    staffWrite: 0,
    provision: 0,
    rosterAction: 0,
    rosterCommit: 0,
  };
  const requests = [],
    holds = new Map();
  function hold(path) {
    let entered, release;
    const began = new Promise((r) => (entered = r)),
      wait = new Promise((r) => (release = r));
    holds.set(path, { entered, wait });
    return {
      entered: began,
      release: () => {
        holds.delete(path);
        release();
      },
    };
  }
  const brief = (c) => ({ ...c, owner_id: owners.get(c.id) });
  const projection = (a) => ({
    ...a,
    assigned_course_count: [...staff.values()].filter((ids) =>
      ids.includes(a.user.id),
    ).length,
    owned_course_count: [...owners.values()].filter((uid) => uid === a.user.id)
      .length,
  });
  const detail = (a) => ({
    ...projection(a),
    staff_courses: courses
      .filter((c) => staff.get(c.id).includes(a.user.id))
      .map(brief),
  });
  const staffResponse = (cid) => ({
    course: brief(courses.find((c) => c.id === cid)),
    staff: staff
      .get(cid)
      .map((uid) => ({
        user: accounts.get(uid).user,
        active: accounts.get(uid).active,
        is_primary: owners.get(cid) === uid,
      })),
  });
  const roster = (cid, archived) =>
    [...enrollments.get(cid).entries()]
      .filter(([, x]) => x === archived)
      .map(([uid, x]) => ({
        user: accounts.get(uid).user,
        archived_at: x ? "2026-10-08T00:00:00Z" : null,
        purge_at: x ? "2026-11-07T00:00:00Z" : null,
        has_work: uid === "student-a",
      }));
  const send = (res, n, data) => {
    res.writeHead(n, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    res.end(JSON.stringify(data));
  };
  const fail = (res) =>
    send(res, 503, { detail: "Synthetic independent GET unavailable" });
  function afterWrite() {
    if (controls.afterWriteReadFailure) {
      controls.afterWriteReadFailure = false;
      controls.failGet = 1;
    }
  }
  function add(name, email, role) {
    const uid = "new-" + ++serial;
    const a = {
      user: {
        id: uid,
        name,
        email,
        role,
        must_change_password: true,
        avatar_url: null,
      },
      active: true,
      archived_at: null,
      purge_at: null,
    };
    accounts.set(uid, a);
    return a;
  }
  function multipart(body, key) {
    const s = body.toString();
    const m = s.match(
      new RegExp(
        'name="' +
          key +
          '"[^\\r\\n]*\\r\\n(?:[^\\r\\n]+\\r\\n)*\\r\\n([\\s\\S]*?)\\r\\n--',
      ),
    );
    return m?.[1] ?? "";
  }
  const plugin = {
    name: "stage11-synthetic-personnel-http",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url, "http://localhost"),
          p = url.pathname,
          m = req.method;
        if (!p.startsWith("/api/")) return next();
        requests.push({ path: p, method: m });
        try {
          const chunks = [];
          for await (const chunk of req) chunks.push(chunk);
          const raw = Buffer.concat(chunks);
          const body = (req.headers["content-type"] ?? "").includes("json")
            ? JSON.parse(raw.toString() || "{}")
            : {};
          if (m === "GET" && holds.has(p)) {
            const snapshot = JSON.stringify(
              p === "/api/admin/users"
                ? null
                : p.startsWith("/api/admin/users/") && !p.includes("/import/")
                  ? detail(accounts.get(p.split("/").at(-1)))
                  : p.endsWith("/staff")
                    ? staffResponse(p.split("/")[3])
                    : null,
            );
            const h = holds.get(p);
            h.entered();
            await h.wait;
            if (snapshot !== "null")
              return send(res, 200, JSON.parse(snapshot));
          }
          if (
            m === "GET" &&
            controls.failGet &&
            p !== "/api/admin/access-settings" &&
            p !== "/api/admin/courses"
          ) {
            controls.failGet--;
            return fail(res);
          }
          if (p === "/api/admin/access-settings") {
            if (m === "PUT") registration = body.registration_enabled;
            return send(res, 200, { registration_enabled: registration });
          }
          if (p === "/api/admin/courses")
            return send(res, 200, { courses: courses.map(brief) });
          if (p === "/api/admin/users/import/preview") {
            counts.preview++;
            const defaultRole = multipart(raw, "default_role") || "student";
            const file = multipart(raw, "file");
            let rows;
            if (raw.includes(Buffer.from("PK\x03\x04"))) {
              rows = [
                {
                  name: "XLSX Student",
                  email: "xlsx-student@example.invalid",
                  role: "student",
                },
                {
                  name: "XLSX Teacher",
                  email: "xlsx-teacher@example.invalid",
                  role: "teacher",
                },
              ];
            } else
              rows = file
                .trim()
                .split(/\r?\n/)
                .slice(1)
                .filter(Boolean)
                .map((line) => {
                  const [name, email, role] = line.split(",");
                  return { name, email, role: role || defaultRole };
                });
            rows = rows.map((row, i) => {
              const existing = [...accounts.values()].find(
                (a) => a.user.email === row.email,
              );
              const errors = controls.previewError
                ? ["Synthetic validation error"]
                : existing && existing.user.role !== row.role
                  ? [
                      "Existing account has another role; change role explicitly.",
                    ]
                  : [];
              return {
                ...row,
                row_number: i + 2,
                action: errors.length ? "error" : existing ? "skip" : "create",
                errors,
                warnings: [],
              };
            });
            controls.previewError = false;
            const preview = {
              import_id: "import-" + ++serial,
              rows,
              valid_count: rows.filter((r) => r.action !== "error").length,
              error_count: rows.filter((r) => r.action === "error").length,
            };
            imports.set(preview.import_id, {
              preview,
              status: "pending",
              result: null,
            });
            return send(res, 200, preview);
          }
          if (p.startsWith("/api/admin/users/import/")) {
            const iid = p.split("/")[5],
              state = imports.get(iid);
            if (m === "GET") {
              counts.importGet++;
              return send(res, 200, state);
            }
            counts.commit++;
            if (!state.result) {
              let created = 0,
                skipped = 0;
              const user_ids = [];
              for (const row of state.preview.rows) {
                let a = [...accounts.values()].find(
                  (a) => a.user.email === row.email,
                );
                if (a) skipped++;
                else {
                  a = add(row.name, row.email, row.role);
                  created++;
                }
                user_ids.push(a.user.id);
              }
              state.status = "committed";
              state.result = { created, skipped, user_ids };
            }
            afterWrite();
            if (controls.unknownCommit) {
              controls.unknownCommit = false;
              return send(res, 503, {
                detail: "Synthetic lost commit response",
              });
            }
            return send(res, 200, state.result);
          }
          if (p === "/api/admin/users" && m === "GET") {
            const q = (url.searchParams.get("q") ?? "").toLowerCase(),
              role = url.searchParams.get("role"),
              active = url.searchParams.get("active");
            const rows = [...accounts.values()]
              .filter(
                (a) =>
                  (!q ||
                    (a.user.name + " " + a.user.email)
                      .toLowerCase()
                      .includes(q)) &&
                  (!role || a.user.role === role) &&
                  (active === null || a.active === (active === "true")),
              )
              .sort(
                (a, b) =>
                  a.user.name.localeCompare(b.user.name) ||
                  a.user.email.localeCompare(b.user.email) ||
                  a.user.id.localeCompare(b.user.id),
              );
            const offset = Number(url.searchParams.get("offset") || 0),
              limit = Number(url.searchParams.get("limit") || 50);
            return send(res, 200, {
              items: rows.slice(offset, offset + limit).map(projection),
              total: rows.length,
              offset,
              limit,
            });
          }
          if (p === "/api/admin/users" && m === "POST") {
            counts.create++;
            const a = add(body.name, body.email, body.role);
            afterWrite();
            if (controls.unknownCreate) {
              controls.unknownCreate = false;
              return send(res, 503, {
                detail: "Synthetic lost create response",
              });
            }
            return send(res, 200, { user: a.user });
          }
          if (/^\/api\/admin\/users\/[^/]+(?:\/status)?$/.test(p)) {
            const uid = p.split("/")[4],
              a = accounts.get(uid);
            if (m === "GET") return send(res, 200, detail(a));
            if (m === "PATCH") {
              counts.role++;
              if (controls.roleConflict) {
                const detail = controls.roleConflict;
                controls.roleConflict = "";
                return send(res, 409, { detail });
              }
              a.user.role = body.role;
              afterWrite();
              return send(res, 200, { user: a.user });
            }
            counts.status++;
            a.active = body.active;
            a.archived_at = body.active ? null : "2026-10-08T00:00:00Z";
            a.purge_at = null;
            afterWrite();
            return send(res, 200, projection(a));
          }
          if (/^\/api\/courses\/[^/]+\/staff/.test(p)) {
            const cid = p.split("/")[3];
            if (m === "GET") return send(res, 200, staffResponse(cid));
            counts.staffWrite++;
            if (controls.staffConflict) {
              const detail = controls.staffConflict;
              controls.staffConflict = "";
              return send(res, 409, { detail });
            }
            if (m === "POST") {
              if (!staff.get(cid).includes(body.user_id))
                staff.get(cid).push(body.user_id);
            } else if (m === "PUT") owners.set(cid, body.user_id);
            else {
              const uid = p.split("/")[5];
              staff.set(
                cid,
                staff.get(cid).filter((x) => x !== uid),
              );
            }
            afterWrite();
            return send(res, 200, staffResponse(cid));
          }
          if (/^\/api\/teacher\/courses\/[^/]+\/students/.test(p)) {
            const cid = p.split("/")[4];
            if (m === "GET")
              return send(
                res,
                200,
                roster(cid, url.searchParams.get("archived") === "true"),
              );
            if (p.endsWith("/archive") || p.endsWith("/restore")) {
              counts.rosterAction++;
              const archived = p.endsWith("/archive");
              for (const uid of body.user_ids)
                enrollments.get(cid).set(uid, archived);
              afterWrite();
              return send(res, 200, { affected_ids: body.user_ids });
            }
            if (p.endsWith("/import/preview")) {
              const preview = {
                import_id: "roster-fixture",
                valid_count: 1,
                error_count: 0,
                rows: [
                  {
                    row_number: 2,
                    name: "Roster Import Student",
                    email: "roster-import@example.invalid",
                    action: "create",
                    errors: [],
                    warnings: [],
                  },
                ],
              };
              imports.set("roster-fixture", { preview });
              return send(res, 200, preview);
            }
            if (p.endsWith("/commit")) {
              counts.rosterCommit++;
              let a = [...accounts.values()].find(
                (a) => a.user.email === "roster-import@example.invalid",
              );
              if (!a)
                a = add(
                  "Roster Import Student",
                  "roster-import@example.invalid",
                  "student",
                );
              enrollments.get(cid).set(a.user.id, false);
              afterWrite();
              return send(res, 200, {
                created: 1,
                enrolled: 0,
                restored: 0,
                skipped: 0,
              });
            }
            counts.provision++;
            let a = [...accounts.values()].find(
              (a) => a.user.email === body.email,
            );
            if (!a) {
              if (!body.temporary_password)
                return send(res, 422, {
                  detail: "A new Student requires a temporary password.",
                });
              a = add(body.name, body.email, "student");
            }
            enrollments.get(cid).set(a.user.id, false);
            afterWrite();
            return send(res, 200, { user: a.user, course_id: cid });
          }
          return send(res, 404, {
            detail: "Unknown synthetic fixture endpoint",
          });
        } catch (e) {
          return send(res, 500, {
            detail: "Synthetic fixture exception: " + e.message,
          });
        }
      });
    },
  };
  return {
    plugin,
    controls,
    counts,
    requests,
    accounts,
    imports,
    staff,
    owners,
    enrollments,
    courses,
    hold,
  };
}
