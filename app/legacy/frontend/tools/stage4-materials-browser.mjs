// Labelled synthetic frontend HTTP fixtures, not database/OCR/model evidence.
import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "..");
const out = path.join(root, "artifacts/stage4-materials");
const checks = [],
  calls = [],
  errors = [],
  library = new Map();
let server,
  browser,
  page,
  sequence = 0,
  rejectG = true,
  failRead = false,
  delayUpload = false;
const clone = (value) => structuredClone(value);
const session = (id) => ({
  id,
  course_id: "course1",
  title: "Synthetic materials",
  subtitle: "",
  number: id === "s1" ? 1 : 2,
  status: "draft",
  question_count: 0,
  estimated_minutes: 10,
  learning_objectives: [],
  instructions: "",
  reference_policy: "after_attempt",
  teaching_language: "en",
  questions: [],
  groups: [],
  materials: [...library.values()]
    .filter((m) => m.session_ids.includes(id))
    .map(clone),
});
const file = (name) => ({
  name,
  mimeType: "text/plain",
  buffer: Buffer.from(`Synthetic reading ${name}.`),
});
const check = (name, detail = {}) =>
  checks.push({ name, passed: true, ...detail });
try {
  await fs.mkdir(out, { recursive: true });
  server = await createServer({
    configFile: false,
    root,
    cacheDir: path.join(out, "vite-cache"),
    plugins: [react()],
    server: { host: "127.0.0.1", port: 0 },
  });
  await server.listen();
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  if (!(await fetch(`${origin}/artifacts/stage4-materials/harness.html`)).ok)
    throw Error("Fixture server not ready");
  if (process.env.TMPDIR) {
    process.env.TEMP = process.env.TMPDIR;
    process.env.TMP = process.env.TMPDIR;
  }
  browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
  });
  await context.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      method = req.method(),
      p = url.pathname;
    const respond = (x, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(x),
      });
    const log = { path: p, method };
    calls.push(log);
    if (p === "/api/courses/course1/materials")
      return respond({ materials: [...library.values()] });
    let match = p.match(/^\/api\/sessions\/(s[12])$/);
    if (match) {
      if (failRead) {
        failRead = false;
        return respond({ detail: "Synthetic readback failure" }, 503);
      }
      return respond(session(match[1]));
    }
    match = p.match(/^\/api\/sessions\/(s[12])\/materials$/);
    if (match && method === "POST") {
      const body = req.postDataBuffer().toString("utf8"),
        name = body.match(/filename="([^"]+)"/)?.[1];
      log.filename = name;
      if (delayUpload) {
        delayUpload = false;
        await new Promise((r) => setTimeout(r, 350));
      }
      if (name === "G.txt" && rejectG) {
        rejectG = false;
        return respond({ detail: "Synthetic individual upload failure" }, 500);
      }
      const id = `m${++sequence}`,
        m = {
          id,
          title: name,
          kind: "reading",
          visibility: "student",
          source_label: name,
          status: "ready",
          excerpt: `Synthetic reading ${name}.`,
          preview_kind: name.endsWith(".pdf") ? "pdf" : "text",
          preview_url: `/api/materials/${id}/preview`,
          download_url: `/api/materials/${id}/download`,
          session_ids: [match[1]],
        };
      library.set(id, m);
      return respond(m);
    }
    match = p.match(/^\/api\/sessions\/(s[12])\/materials\/attach$/);
    if (match) {
      const m = library.get(req.postDataJSON().material_id);
      if (!m.session_ids.includes(match[1])) m.session_ids.push(match[1]);
      return respond(m);
    }
    match = p.match(/^\/api\/sessions\/(s[12])\/materials\/(m\d+)$/);
    if (match && method === "DELETE") {
      const m = library.get(match[2]);
      m.session_ids = m.session_ids.filter((s) => s !== match[1]);
      return respond({ ok: true });
    }
    match = p.match(/^\/api\/materials\/(m\d+)\/preview$/);
    if (match)
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: await fs.readFile(path.join(out, "preview.pdf")),
      });
    return respond(
      { detail: `Unexpected synthetic fixture route ${method} ${p}` },
      404,
    );
  });
  page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${origin}/artifacts/stage4-materials/harness.html`);
  await expect(
    page.getByRole("heading", { name: "Session Materials", exact: true }),
  ).toBeVisible();
  const picker = page.getByLabel("Choose files", { exact: true }),
    upload = page.getByRole("button", {
      name: "Upload selected files",
      exact: true,
    });
  const uploadFiles = async (names) => {
    await picker.setInputFiles(names.map(file));
    await upload.click();
    await expect(
      page.getByText(
        "Uploaded files verified in Session Materials and Course Materials. Review extraction before publishing.",
        { exact: true },
      ),
    ).toBeVisible();
  };
  await expect(picker).toHaveAttribute("multiple", "");
  await uploadFiles(["A.txt", "B.txt", "C.txt"]);
  await expect(page.locator(".material-card")).toHaveCount(3);
  check("one action uploads multiple files to S1");
  await page.getByRole("button", { name: "Session 2", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Session 2", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".material-card")).toHaveCount(0);
  check("S2 initially shows no S1 material cards");
  await uploadFiles(["D.txt", "E.txt"]);
  const B = [...library.values()].find((m) => m.title === "B.txt");
  await page.getByLabel("Course Materials", { exact: true }).selectOption(B.id);
  await page
    .getByRole("button", { name: "Add to this session", exact: true })
    .click();
  await expect(page.locator(".material-card")).toHaveCount(3);
  expect(
    session("s1")
      .materials.map((m) => m.title)
      .sort(),
  ).toEqual(["A.txt", "B.txt", "C.txt"]);
  expect(
    session("s2")
      .materials.map((m) => m.title)
      .sort(),
  ).toEqual(["B.txt", "D.txt", "E.txt"]);
  expect(library.size).toBe(5);
  check("A/B/C and B/D/E memberships with five shared course files");
  const bCard = page
    .locator(".material-card")
    .filter({ has: page.getByRole("heading", { name: "B.txt", exact: true }) });
  await bCard
    .getByRole("button", { name: "Remove from this session", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm removal", exact: true })
    .click();
  await expect(page.locator(".material-card")).toHaveCount(2);
  expect(B.session_ids).toEqual(["s1"]);
  check("session removal retains file and S1 membership");
  await uploadFiles(["F.txt", "G.txt"]);
  await expect(
    page.getByRole("button", { name: "Retry G.txt", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry G.txt", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Retry G.txt", exact: true }),
  ).toHaveCount(0);
  expect(calls.filter((c) => c.filename === "F.txt")).toHaveLength(1);
  expect(calls.filter((c) => c.filename === "G.txt")).toHaveLength(2);
  check("partial upload failure retries only failed file");
  await picker.setInputFiles([file("H.txt")]);
  failRead = true;
  await upload.click();
  await expect(
    page.getByText("Synthetic readback failure", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Upload selected files", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Refresh status", exact: true })
    .click();
  await expect(
    page.getByText("Materials refreshed.", { exact: true }),
  ).toBeVisible();
  expect(calls.filter((c) => c.filename === "H.txt")).toHaveLength(1);
  check("failed readback does not re-upload accepted file");
  await uploadFiles(["Preview.pdf"]);
  const pdf = page
    .locator(".material-card")
    .filter({
      has: page.getByRole("heading", { name: "Preview.pdf", exact: true }),
    });
  const popupPromise = context.waitForEvent("page");
  await pdf
    .getByRole("link", { name: "Open authenticated preview", exact: true })
    .click();
  const popup = await popupPromise;
  await popup.waitForURL(/\/api\/materials\/m\d+\/preview/);
  await expect(page.locator("iframe")).toHaveCount(0);
  await popup.close();
  check("PDF opens authenticated top-level route without iframe");
  await page.screenshot({
    path: path.join(out, "desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".course-material-picker").scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel("Course Materials", { exact: true }).click();
  await page.keyboard.press("Escape");
  await page.screenshot({ path: path.join(out, "mobile.png"), fullPage: true });
  check("mobile controls fit and library picker is reachable");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await picker.setInputFiles([file("I.txt"), file("J.txt")]);
  delayUpload = true;
  const response = page.waitForResponse(
    (r) =>
      r.url().includes("/api/sessions/s2/materials") &&
      r.request().method() === "POST",
  );
  await upload.click();
  await page
    .getByRole("button", {
      name: "Force navigation for lifecycle check",
      exact: true,
    })
    .click();
  await response;
  await expect(
    page.getByRole("heading", { name: "Session 1", exact: true }),
  ).toBeVisible();
  expect(calls.filter((c) => c.filename === "I.txt")).toHaveLength(1);
  expect(calls.filter((c) => c.filename === "J.txt")).toHaveLength(0);
  await expect(page.locator(".material-card")).toHaveCount(3);
  check(
    "navigation stops queued work and old response cannot overwrite new session",
  );
  expect(errors).toEqual([]);
  check("no browser page errors");
  await fs.writeFile(
    path.join(out, "result.json"),
    JSON.stringify(
      {
        status: "passed",
        evidence:
          "Synthetic frontend HTTP fixtures only; not SQLite/OCR/model evidence",
        checks,
        calls,
        page_errors: errors,
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      status: "passed",
      checks: checks.length,
      report: path.join(out, "result.json"),
    }),
  );
} catch (e) {
  await fs.mkdir(out, { recursive: true });
  if (page) {
    await page
      .screenshot({ path: path.join(out, "failure.png"), fullPage: true })
      .catch(() => {});
    await fs
      .writeFile(path.join(out, "failure.html"), await page.content())
      .catch(() => {});
  }
  await fs.writeFile(
    path.join(out, "failure.json"),
    JSON.stringify(
      { error: String(e), checks, calls, page_errors: errors },
      null,
      2,
    ),
  );
  throw e;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
}
