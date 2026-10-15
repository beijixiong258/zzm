// Synthetic HTTP only. No providers, credentials, backend or SQLite.
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
const copy = (x) => structuredClone(x);
const unchecked = () => ({
  status: "not_checked",
  checked_at: null,
  message: null,
});
export async function serveSettingsFixture(built) {
  const fixture = {
    logs: [],
    modelReadFail: 0,
    searchReadFail: 0,
    modelWriteFail: false,
    searchWriteFail: false,
    modelTestFail: false,
    searchTestFail: false,
    delayModelRead: 0,
    delaySearchRead: 0,
    mismatchModel: false,
    mismatchSearch: false,
    modelDelayWrite: 0,
    searchDelayWrite: 0,
  };
  fixture.releases = [];
  fixture.holdRead = (name) => {
    let release;
    const promise = new Promise((resolve) => {
      release = resolve;
    });
    fixture[`${name}ReadGate`] = promise;
    fixture.releases.push(release);
    return release;
  };
  fixture.releaseAll = () => {
    for (const release of fixture.releases) release();
    fixture.releases = [];
  };
  fixture.reset = () => {
    fixture.model = {
      ai: {
        mode: "openai",
        configured: true,
        base_url: "http://fixture.invalid/v1",
        model: "Fixture teaching model",
        connection: unchecked(),
      },
      api_key_set: true,
    };
    fixture.search = {
      provider: "tavily",
      enabled: true,
      configured: true,
      api_key_set: true,
      api_key_source: "environment",
      connection: unchecked(),
    };
    fixture.user = {
      id: "fixture-admin",
      name: "Alex Fixture",
      email: "alex@example.invalid",
      role: "admin",
      is_demo: false,
    };
    for (const k of [
      "modelReadFail",
      "searchReadFail",
      "delayModelRead",
      "delaySearchRead",
      "modelDelayWrite",
      "searchDelayWrite",
    ])
      fixture[k] = 0;
    for (const k of [
      "modelWriteFail",
      "searchWriteFail",
      "modelTestFail",
      "searchTestFail",
      "mismatchModel",
      "mismatchSearch",
    ])
      fixture[k] = false;
  };
  fixture.reset();
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://fixture.local"),
        p = url.pathname;
      const json = (status, body) => {
        res.writeHead(status, {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        });
        res.end(JSON.stringify(body));
      };
      if (p.startsWith("/api/")) {
        let body = "";
        for await (const chunk of req) body += chunk;
        const b = body ? JSON.parse(body) : {};
        // Safe request facts only; no submitted keys or key lengths are retained.
        fixture.logs.push({
          path: p,
          method: req.method,
          fields: Object.keys(b),
          mode: b.mode,
          enabled: b.enabled,
          has_key: Object.hasOwn(b, "api_key"),
          clear_key: b.api_key === "" || b.clear_api_key === true,
        });
        const model = p === "/api/teacher/settings",
          search = p === "/api/teacher/search-settings";
        if ((model || search) && req.method === "GET") {
          const name = model ? "model" : "search",
            snapshot = copy(fixture[name]);
          const delay = fixture[model ? "delayModelRead" : "delaySearchRead"];
          fixture[model ? "delayModelRead" : "delaySearchRead"] = 0;
          const gate = fixture[`${name}ReadGate`];
          fixture[`${name}ReadGate`] = null;
          if (gate) await gate;
          await pause(delay);
          const fail = model ? "modelReadFail" : "searchReadFail";
          if (fixture[fail] > 0) {
            fixture[fail]--;
            return json(503, { detail: "Synthetic readback failure." });
          }
          if (model && fixture.mismatchModel)
            snapshot.ai.model = "Synthetic conflicting model";
          if (search && fixture.mismatchSearch)
            snapshot.enabled = !snapshot.enabled;
          return json(200, snapshot);
        }
        if ((model || search) && req.method === "PUT") {
          await pause(fixture[model ? "modelDelayWrite" : "searchDelayWrite"]);
          if (fixture[model ? "modelWriteFail" : "searchWriteFail"])
            return json(422, { detail: "Synthetic rejected configuration." });
          if (model) {
            fixture.model.ai = {
              ...fixture.model.ai,
              mode: b.mode,
              base_url: b.base_url.replace(/\/+$/, ""),
              model: b.model,
              configured: !!(b.base_url && b.model),
              connection: unchecked(),
            };
            if (Object.hasOwn(b, "api_key"))
              fixture.model.api_key_set = !!b.api_key;
            return json(200, fixture.model);
          }
          fixture.search.enabled = b.enabled;
          if (b.clear_api_key) {
            fixture.search.api_key_set = false;
            fixture.search.api_key_source = "none";
          } else if (b.api_key) {
            fixture.search.api_key_set = true;
            fixture.search.api_key_source = "saved";
          }
          fixture.search.configured = fixture.search.api_key_set;
          fixture.search.connection = fixture.search.configured
            ? unchecked()
            : { status: "not_configured", checked_at: null, message: null };
          return json(200, fixture.search);
        }
        if (
          p === "/api/teacher/settings/test" ||
          p === "/api/teacher/search-settings/test"
        ) {
          const isModel = p.includes("/settings/test"),
            failure = fixture[isModel ? "modelTestFail" : "searchTestFail"];
          const connection = {
            status: failure ? "error" : "connected",
            checked_at: "2026-10-08T01:00:00Z",
            message: failure
              ? "Synthetic provider failure."
              : "Synthetic fixture check.",
          };
          if (isModel) fixture.model.ai.connection = connection;
          else fixture.search.connection = connection;
          if (failure)
            return json(503, { detail: "Synthetic provider failure." });
          return json(
            200,
            isModel
              ? {
                  ok: true,
                  message: "Synthetic fixture check.",
                  model: fixture.model.ai.model,
                  mode: "openai",
                }
              : {
                  ok: true,
                  message: "Synthetic fixture check.",
                  result_count: 2,
                  connection,
                },
          );
        }
        if (p === "/api/auth/profile") {
          fixture.user.name = b.name;
          return json(200, { user: fixture.user });
        }
        if (p === "/api/auth/me") return json(200, { user: fixture.user });
        if (p === "/api/admin/teachers" || p === "/api/admin/students")
          return json(200, []);
        return json(404, { detail: "Unimplemented fixture route." });
      }
      const target =
        p === "/"
          ? path.join(built, "tests/stage7-settings-harness.html")
          : path.join(built, p.slice(1));
      if (!target.startsWith(built))
        return json(403, { detail: "Outside fixture." });
      const ext = path.extname(target),
        content = await fs.readFile(target);
      res.writeHead(200, {
        "Content-Type":
          {
            ".html": "text/html",
            ".js": "text/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
            ".png": "image/png",
          }[ext] ?? "application/octet-stream",
      });
      res.end(content);
    } catch {
      res.writeHead(500);
      res.end("Synthetic fixture error");
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return { fixture, server, url: `http://127.0.0.1:${server.address().port}` };
}
