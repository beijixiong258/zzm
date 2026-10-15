// Real installed Chrome, built React, local HTTP; UI ONLY, not auth/OCR/model acceptance.
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const artifacts = path.resolve(root, "../artifacts/stage13/ui");
const scratch = await fs.mkdtemp(
  "C:/Users/17193/AppData/Local/hermes/cache/scratch/stage13-ui-owned-",
);
await fs.mkdir(path.join(artifacts, "screenshots"), { recursive: true });
const stamp = "2026-10-10T00:00:00Z";
const info = (rid = "r1") => ({
  revision_id: rid,
  source_sha256: "a".repeat(64),
  page_count: 317,
  block_count: 951,
  quality: "needs_review",
  review_count: 1,
  parser: { name: "UI-only synthetic", version: "1", recipe: "Not OCR" },
  created_at: stamp,
  warnings: [
    "Known diagram uncertainty — inspect source. No universal accuracy claim.",
  ],
});
let account = "staff-a",
  available = true,
  current = info(),
  job = null,
  serial = 0,
  lostJob = false,
  lostReview = false,
  receiptFail = 0,
  reviewConflict = false,
  holdPage = false;
const held = [],
  logs = [],
  requests = new Map(),
  reviews = new Map(),
  corrected = new Map();
const material = {
  id: "m1",
  title: "Synthetic 317-page PDF",
  kind: "reading",
  visibility: "student",
  source_label: "UI-only source",
  status: "ready",
  excerpt: "Preview only",
  preview_kind: "pdf",
  preview_url: "/api/materials/m1/preview",
  download_url: "/api/materials/m1/download",
};
let uploadRows = [];
const pages = () =>
  Array.from({ length: 317 }, (_, i) => ({
    number: i + 1,
    printed_label: i === 268 ? "A147" : i === 316 ? "End" : null,
    status: i === 268 ? "needs_review" : "text",
    block_count: 3,
    review_count: i === 268 ? 1 : 0,
  }));
const pageData = (mid, n, rid, vid) => {
  const asset = (name) =>
    `/api/materials/${mid}/document/assets/${name}?revision_id=${rid}${vid ? "&version_id=" + vid : ""}`;
  const text = `<table><tr><td>Literal source table on PDF page ${n}</td></tr></table>\n<img src=x onerror=alert(1)>`;
  const block = {
    id: `p${n}-b1`,
    type: "table",
    bbox: [0.1, 0.1, 0.9, 0.4],
    text,
    quality: "needs_review",
    issues: ["Ambiguous relationship"],
    assets: [],
    parent_id: null,
  };
  const correction = corrected.get(rid + ":" + block.id);
  if (correction)
    Object.assign(block, correction, {
      raw_text: text,
      review: { by: "staff-a", at: stamp, reason: correction.reason },
    });
  return {
    number: n,
    printed_label: n === 269 ? "A147" : n === 317 ? "End" : null,
    status: "needs_review",
    rotation: 0,
    image_url: asset("pages/p" + n + ".svg"),
    width: 600,
    height: 800,
    issues: ["Synthetic quality warning"],
    blocks: [
      block,
      {
        id: `p${n}-b2`,
        type: "image",
        bbox: [0.15, 0.5, 0.85, 0.8],
        text: "Original diagram",
        quality: "needs_review",
        issues: [],
        assets: [
          asset("assets/crop.svg"),
          "https://outside.invalid/never-load.png",
        ],
        parent_id: null,
      },
      {
        id: `p${n}-b3`,
        type: "caption",
        bbox: [0.15, 0.8, 0.85, 0.9],
        text: "Nested diagram caption",
        quality: "extracted",
        issues: [],
        assets: [],
        parent_id: `p${n}-b2`,
      },
    ],
  };
};
const summary = (vid) => ({
  document: vid
    ? info(vid === "edition-old" ? "old-r1" : "student-r1")
    : current,
  latest_job: vid ? null : job,
  pages: current || vid ? pages() : [],
});
function json(res, obj, status = 200) {
  if (res.destroyed) return;
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(obj));
}
let server, context, url, page;
const result = {
  label:
    "UI-only synthetic HTTP fixture; no backend authentication/SQLite/OCR/model/production proof",
  checks: [],
  screenshots: [],
  errors: [],
  external: [],
  requests: logs,
  cleanup: {},
  scratch,
};
async function check(name, fn) {
  await fn();
  result.checks.push({ name, passed: true });
  console.log("PASS " + name);
}
async function shot(name) {
  const file = path.join(artifacts, "screenshots", name + ".png");
  await page.screenshot({ path: file, fullPage: false });
  result.screenshots.push(file);
}
const open = async () => {
  await page
    .getByRole("button", { name: "Full PDF / processing status", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByText("Loading document…", { exact: true }),
  ).toHaveCount(0);
};
const close = async () => {
  await page
    .getByRole("button", { name: "Close document reader", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
};
try {
  await build({
    root,
    configFile: false,
    plugins: [react()],
    cacheDir: path.join(scratch, "vite-cache"),
    build: {
      outDir: path.join(scratch, "built"),
      emptyOutDir: true,
      rollupOptions: {
        input: path.join(root, "tests/stage12-document-harness.html"),
      },
    },
  });
  server = http.createServer(async (req, res) => {
    try {
      const u = new URL(req.url, "http://local"),
        p = u.pathname,
        method = req.method;
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const body = Buffer.concat(chunks).toString();
      if (p.startsWith("/api/"))
        logs.push({
          method,
          path: p,
          query: u.search,
          body:
            method === "POST" && p.includes("/document/")
              ? JSON.parse(body)
              : undefined,
        });
      if (p === "/api/auth/me")
        return json(res, {
          user: { id: account, role: "teacher", name: "Synthetic staff" },
        });
      if (p === "/api/document-processing")
        return json(res, {
          available,
          formats: ["pdf"],
          max_upload_bytes: 25 * 1024 * 1024,
          max_pages: 1000,
        });
      if (p === "/api/courses/c1/materials")
        return json(res, {
          materials: [material, ...uploadRows].map((m) => ({
            ...m,
            session_ids: ["s1"],
          })),
        });
      if (p === "/api/sessions/s1")
        return json(res, {
          id: "s1",
          course_id: "c1",
          title: "Synthetic session",
          subtitle: "",
          number: 1,
          status: "draft",
          question_count: 0,
          estimated_minutes: 10,
          learning_objectives: [],
          instructions: "",
          teaching_language: "en",
          reference_policy: "after_attempt",
          questions: [],
          groups: [],
          materials: [material, ...uploadRows],
        });
      if (p === "/api/sessions/s1/materials" && method === "POST") {
        const full = body.includes("full_document");
        const m = {
          ...material,
          id: "uploaded-" + ++serial,
          title: "Synthetic upload",
          source_label: "Synthetic upload",
          status: "processing",
          excerpt: "",
          preview_url: "/api/materials/uploaded-" + serial + "/preview",
          download_url: "/api/materials/uploaded-" + serial + "/download",
        };
        uploadRows.push({
          ...m,
          status: full ? "needs_review" : "ready",
          excerpt: "Background job completed before GET",
          document: full ? info("upload-r") : null,
        });
        logs.at(-1).processing = full ? "full_document" : "preview";
        return json(res, m);
      }
      const m = p.match(/^\/api\/materials\/([^/]+)\/document(.*)$/);
      if (m) {
        const mid = m[1],
          tail = m[2],
          vid = u.searchParams.get("version_id");
        if (tail === "") return json(res, summary(vid));
        if (tail.startsWith("/assets/")) {
          res.writeHead(200, { "Content-Type": "image/svg+xml" });
          return res.end(
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800"><rect width="600" height="800" fill="#fff"/><text x="35" y="50" font-size="21">SYNTHETIC RETAINED SOURCE IMAGE</text><rect x="60" y="80" width="480" height="240" fill="#e2eade"/><text x="65" y="150">Literal table source region</text><rect x="90" y="400" width="420" height="240" fill="#bdd0ba"/></svg>',
          );
        }
        const pm = tail.match(/^\/pages\/(\d+)$/);
        if (pm) {
          const value = pageData(
            mid,
            Number(pm[1]),
            u.searchParams.get("revision_id"),
            vid,
          );
          if (holdPage && mid === "m1") {
            held.push(() => json(res, value));
            return;
          }
          return json(res, value);
        }
        if (tail === "/jobs" && method === "POST") {
          const payload = JSON.parse(body);
          job = {
            id: "job-" + ++serial,
            material_id: mid,
            status: "queued",
            created_at: stamp,
            started_at: null,
            finished_at: null,
            page_count: 317,
            processed_pages: 0,
            error: null,
            revision_id: null,
          };
          requests.set(payload.request_id, job);
          if (lostJob) {
            lostJob = false;
            return json(
              res,
              {
                detail: "Synthetic accepted job, acknowledgement lost upstream",
              },
              502,
            );
          }
          return json(res, job);
        }
        if (tail.startsWith("/jobs/requests/")) {
          if (receiptFail > 0) {
            receiptFail--;
            return json(res, { detail: "Synthetic unavailable receipt" }, 404);
          }
          return json(
            res,
            requests.get(decodeURIComponent(tail.slice(15))) || {
              detail: "Not found",
            },
          );
        }
        if (tail.startsWith("/jobs/")) return json(res, job);
        if (tail === "/reviews" && method === "POST") {
          if (reviewConflict) {
            reviewConflict = false;
            current = info("concurrent-r");
            return json(
              res,
              { detail: "Synthetic stale revision conflict" },
              409,
            );
          }
          const payload = JSON.parse(body);
          if (payload.expected_revision !== current?.revision_id)
            return json(res, { detail: "Stale revision" }, 409);
          current = { ...info("review-" + ++serial), review_count: 2 };
          for (const c of payload.changes)
            corrected.set(current.revision_id + ":" + c.block_id, c);
          reviews.set(payload.request_id, { document: current });
          if (lostReview) {
            lostReview = false;
            return json(
              res,
              {
                detail:
                  "Synthetic accepted review, acknowledgement lost upstream",
              },
              502,
            );
          }
          return json(res, { document: current });
        }
        if (tail.startsWith("/reviews/")) {
          if (receiptFail > 0) {
            receiptFail--;
            return json(res, { detail: "Synthetic receipt unavailable" }, 404);
          }
          return json(
            res,
            reviews.get(decodeURIComponent(tail.slice(9))) || {
              detail: "Not found",
            },
          );
        }
      }
      if (p.match(/^\/api\/materials\/[^/]+\/(preview|download)$/)) {
        res.writeHead(200, { "Content-Type": "text/html" });
        return res.end(
          "<h1>UI-only synthetic original PDF endpoint</h1><p>Original retained; not native PDF-renderer acceptance.</p>",
        );
      }
      if (p.startsWith("/api/"))
        return json(res, { detail: "Unimplemented UI fixture " + p }, 404);
      const file = path.join(
        scratch,
        "built",
        p === "/"
          ? "tests/stage12-document-harness.html"
          : decodeURIComponent(p),
      );
      const content = await fs.readFile(file);
      const ext = path.extname(file);
      res.writeHead(200, {
        "Content-Type":
          {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
          }[ext] || "application/octet-stream",
      });
      res.end(content);
    } catch (e) {
      if (!res.destroyed) json(res, { detail: String(e) }, 500);
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  url = "http://127.0.0.1:" + server.address().port;
  result.origin = url;
  context = await chromium.launchPersistentContext(
    path.join(scratch, "chrome-profile"),
    {
      executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
      headless: true,
      viewport: { width: 1440, height: 1000 },
      serviceWorkers: "block",
    },
  );
  await context.route("**/*", async (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== url && !["data:", "blob:"].includes(u.protocol)) {
      result.external.push(u.href);
      await route.abort();
    } else await route.continue();
  });
  page = context.pages()[0];
  page.on("pageerror", (e) => result.errors.push(String(e)));
  page.on("dialog", (d) => d.accept());
  await page.goto(url);
  await open();
  await check(
    "317-page selection, late pages, printed labels, literal HTML, crops/caption associations and source bbox",
    async () => {
      await expect(
        page.getByLabel("PDF page", { exact: true }).locator("option"),
      ).toHaveCount(317);
      await page.getByLabel("PDF page", { exact: true }).selectOption("269");
      await expect(
        page.getByRole("heading", {
          name: "PDF page 269 · printed A147 · needs review",
        }),
      ).toBeVisible();
      await expect(page.locator('[data-block-id="p269-b1"] pre')).toContainText(
        "<table>",
      );
      await expect(
        page.locator(".document-blocks table,.document-blocks script"),
      ).toHaveCount(0);
      await expect(page.locator(".document-crop")).toBeVisible();
      await expect(
        page.getByText("Associated captions/children: p269-b3", {
          exact: true,
        }),
      ).toBeVisible();
      await page
        .locator('[data-block-id="p269-b1"]')
        .getByRole("button", { name: "Locate on page" })
        .click();
      await expect(page.getByLabel("Source coordinates p269-b1")).toBeVisible();
      await expect(page.locator(".document-image-canvas>img")).toHaveJSProperty(
        "naturalWidth",
        600,
      );
      await shot("desktop-page269");
      await page.getByLabel("PDF page", { exact: true }).selectOption("317");
      await expect(
        page.getByRole("heading", {
          name: "PDF page 317 · printed End · needs review",
        }),
      ).toBeVisible();
    },
  );
  await check(
    "explicit single-block review, independent GET receipt+summary+page, raw text and audit",
    async () => {
      await page
        .locator('[data-block-id="p317-b1"]')
        .getByRole("button", { name: "Review this source block" })
        .click();
      await page
        .getByLabel("Checked source text")
        .fill("Checked synthetic text");
      await page
        .getByLabel("Source-review reason")
        .fill("Compared retained original");
      await page
        .getByRole("button", { name: "Save checked block (not publish)" })
        .click();
      await expect(
        page.getByText(/Source review saved and independently verified/),
      ).toBeVisible();
      await expect(page.getByLabel("Explicit source review")).toHaveCount(0);
      await page
        .getByText("Preserved raw transcription", { exact: true })
        .click();
      await expect(page.locator('[data-block-id="p317-b1"]')).toContainText(
        "<table>",
      );
      await expect
        .poll(
          () =>
            logs.filter(
              (x) => x.method === "GET" && x.path.includes("/reviews/"),
            ).length,
        )
        .toBeGreaterThan(0);
      await expect
        .poll(() => page.evaluate(() => window.stage12.dirty()))
        .toBe(false);
    },
  );
  await check(
    "409 correction retained; refresh + explicit reconfirm rather than auto-rePOST",
    async () => {
      await page
        .locator('[data-block-id="p317-b1"]')
        .getByRole("button", { name: "Review this source block" })
        .click();
      await page
        .getByLabel("Checked source text")
        .fill("Retained correction after 409");
      await page.getByLabel("Source-review reason").fill("Rechecked source");
      reviewConflict = true;
      const posts = logs.filter(
        (x) => x.method === "POST" && x.path.endsWith("/reviews"),
      ).length;
      await page
        .getByRole("button", { name: "Save checked block (not publish)" })
        .click();
      await expect(
        page.getByText("Synthetic stale revision conflict", { exact: true }),
      ).toBeVisible();
      await expect(page.getByLabel("Checked source text")).toHaveValue(
        "Retained correction after 409",
      );
      await expect(
        page.getByRole("button", { name: "Save checked block (not publish)" }),
      ).toBeDisabled();
      await page.getByRole("button", { name: "Refresh source status" }).click();
      await expect(
        page.getByRole("button", {
          name: "Use refreshed revision after checking",
        }),
      ).toBeEnabled();
      await expect(page.getByLabel("Checked source text")).toHaveValue(
        "Retained correction after 409",
      );
      expect(
        logs.filter((x) => x.method === "POST" && x.path.endsWith("/reviews"))
          .length,
      ).toBe(posts + 1);
      await page
        .getByRole("button", { name: "Use refreshed revision after checking" })
        .click();
      await page.getByRole("button", { name: "Discard correction" }).click();
    },
  );
  await check(
    "unknown accepted review response persists and recovers by GET only after reload",
    async () => {
      await page
        .locator('[data-block-id="p317-b1"]')
        .getByRole("button", { name: "Review this source block" })
        .click();
      await page
        .getByLabel("Checked source text")
        .fill("Unknown accepted review");
      await page
        .getByLabel("Source-review reason")
        .fill("Compared original despite lost reply");
      lostReview = true;
      receiptFail = 1;
      await page
        .getByRole("button", { name: "Save checked block (not publish)" })
        .click();
      await expect(
        page.getByLabel("Unconfirmed document request"),
      ).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "Inspect request outcome (GET only)",
        }),
      ).toBeEnabled();
      const posts = logs.filter(
        (x) => x.method === "POST" && x.path.endsWith("/reviews"),
      ).length;
      await page.reload();
      await open();
      await expect(page.getByLabel("Checked source text")).toHaveValue(
        "Unknown accepted review",
      );
      await page
        .getByRole("button", { name: "Inspect request outcome (GET only)" })
        .click();
      await expect(
        page.getByText(/Source review saved and independently verified/),
      ).toBeVisible();
      expect(
        logs.filter((x) => x.method === "POST" && x.path.endsWith("/reviews"))
          .length,
      ).toBe(posts);
    },
  );
  await check(
    "unknown accepted job recovers exact request by GET only; queued/running/completed",
    async () => {
      lostJob = true;
      receiptFail = 1;
      await page
        .getByRole("button", { name: "Reprocess complete document" })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Inspect request outcome (GET only)",
        }),
      ).toBeEnabled();
      const posts = logs.filter(
        (x) => x.method === "POST" && x.path.endsWith("/jobs"),
      ).length;
      await page
        .getByRole("button", { name: "Inspect request outcome (GET only)" })
        .click();
      await expect(
        page.getByText("Queued for full document processing", { exact: true }),
      ).toBeVisible();
      expect(
        logs.filter((x) => x.method === "POST" && x.path.endsWith("/jobs"))
          .length,
      ).toBe(posts);
      job.status = "running";
      job.started_at = stamp;
      await expect(
        page.getByText("Processing complete document…", { exact: true }),
      ).toBeVisible({ timeout: 8000 });
      await expect(
        page.getByRole("button", { name: "Reprocess complete document" }),
      ).toBeDisabled();
      current = info("job-complete");
      job.status = "completed";
      job.revision_id = current.revision_id;
      job.processed_pages = 317;
      job.finished_at = stamp;
      await expect(
        page.getByText("Complete document saved", { exact: true }),
      ).toBeVisible({ timeout: 8000 });
    },
  );
  await check(
    "failed processing retains original and prior good document; retry is explicit",
    async () => {
      job.status = "failed";
      job.error = "Synthetic CPU failure";
      await page.getByRole("button", { name: "Refresh source status" }).click();
      await expect(
        page.getByText("Processing failed — the original is retained", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByRole("link", { name: /Open original PDF/ }),
      ).toBeVisible();
      await expect(page.getByLabel("Document summary")).toContainText(
        "317 PDF pages",
      );
      await shot("failed-original-retained");
    },
  );
  await close();
  await check(
    "student and immutable history: edition/revision pinned, no processing/review controls",
    async () => {
      for (const mode of ["student", "history"]) {
        await page
          .getByRole("button", { name: mode + " fixture", exact: true })
          .click();
        await open();
        await page.getByLabel("PDF page", { exact: true }).selectOption("269");
        await expect(
          page.getByRole("heading", { name: /PDF page 269/ }),
        ).toBeVisible();
        await expect(
          page.getByRole("button", { name: "Review this source block" }),
        ).toHaveCount(0);
        await expect(
          page.getByRole("button", {
            name: /complete PDF|full PDF processing/,
          }),
        ).toHaveCount(0);
        await expect(page.getByLabel("Background job status")).toHaveCount(0);
        expect(
          await page.locator(".document-image-canvas>img").getAttribute("src"),
        ).toContain(
          "version_id=edition-" + (mode === "history" ? "old" : "student"),
        );
        await close();
      }
    },
  );
  await check(
    "late held page GET cannot overwrite another material generation",
    async () => {
      await page
        .getByRole("button", { name: "teacher fixture", exact: true })
        .click();
      holdPage = true;
      await open();
      await expect.poll(() => held.length).toBeGreaterThan(0);
      await page.evaluate(() => window.stage12.setMode("other"));
      await expect(page.getByRole("dialog")).toHaveCount(0);
      holdPage = false;
      for (const release of held.splice(0)) release();
      await open();
      await expect(
        page.getByRole("heading", { name: "Other source · complete document" }),
      ).toBeVisible();
      await expect(page.locator(".document-image-canvas>img")).toHaveAttribute(
        "src",
        /\/m2\/document\/assets\//,
      );
      await close();
    },
  );
  await check(
    "accepted full upload readback may finish before GET, refresh never uploads it twice",
    async () => {
      await page
        .getByRole("button", { name: "manager fixture", exact: true })
        .click();
      await expect(
        page.getByText(/PDF: complete document processing in the background/),
      ).toBeVisible();
      await page
        .getByLabel("Choose files")
        .setInputFiles({
          name: "synthetic.pdf",
          mimeType: "application/pdf",
          buffer: Buffer.from("%PDF UI-only synthetic fixture"),
        });
      await page.getByRole("button", { name: "Upload selected files" }).click();
      await expect(
        page.getByText(
          /Original files saved in the session and course library/,
        ),
      ).toBeVisible();
      await expect(
        page.locator('[data-upload-state="uploaded"]'),
      ).toContainText("Original saved");
      const posts = logs.filter(
        (x) => x.method === "POST" && x.path === "/api/sessions/s1/materials",
      ).length;
      expect(
        logs
          .filter(
            (x) =>
              x.method === "POST" && x.path === "/api/sessions/s1/materials",
          )
          .at(-1).processing,
      ).toBe("full_document");
      await page
        .getByRole("button", { name: "Refresh status", exact: true })
        .click();
      await expect(
        page.getByText("Materials refreshed.", { exact: true }),
      ).toBeVisible();
      expect(
        logs.filter(
          (x) => x.method === "POST" && x.path === "/api/sessions/s1/materials",
        ).length,
      ).toBe(posts);
    },
  );
  await check(
    "unconfigured and non-PDF uploads remain visibly preview only",
    async () => {
      await page
        .getByLabel("Choose files")
        .setInputFiles({
          name: "synthetic.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("fixture"),
        });
      await expect(page.locator('[data-upload-state="queued"]')).toContainText(
        "preview only",
      );
      await page.getByRole("button", { name: "Upload selected files" }).click();
      await expect(
        page.locator('[data-upload-state="uploaded"]'),
      ).toBeVisible();
      expect(
        logs
          .filter(
            (x) =>
              x.method === "POST" && x.path === "/api/sessions/s1/materials",
          )
          .at(-1).processing,
      ).toBe("preview");
      available = false;
      await page.reload();
      await page
        .getByRole("button", { name: "manager fixture", exact: true })
        .click();
      await expect(
        page.getByText(
          /Complete document processing is unavailable or not yet confirmed/,
        ),
      ).toBeVisible();
      await page
        .getByLabel("Choose files")
        .setInputFiles({
          name: "unconfigured.pdf",
          mimeType: "application/pdf",
          buffer: Buffer.from("fixture"),
        });
      await expect(page.locator('[data-upload-state="queued"]')).toContainText(
        "preview only",
      );
      available = true;
    },
  );
  await check(
    "account-scoped draft never restored for a different account",
    async () => {
      await page.reload();
      await open();
      await page
        .locator('[data-block-id="p1-b1"]')
        .getByRole("button", { name: "Review this source block" })
        .click();
      await page
        .getByLabel("Checked source text")
        .fill("staff-a private browser correction");
      await close();
      account = "staff-b";
      await page.evaluate(() => window.stage12.setAccount("staff-b"));
      await open();
      await expect(page.getByLabel("Checked source text")).toHaveCount(0);
      await close();
      account = "staff-a";
      await page.evaluate(() => window.stage12.setAccount("staff-a"));
      await open();
      await expect(page.getByLabel("Checked source text")).toHaveValue(
        "staff-a private browser correction",
      );
      await page.getByRole("button", { name: "Discard correction" }).click();
      await close();
    },
  );
  await check(
    "390px page viewer fit, image zoom, retained block and reachable original citation in nested chat",
    async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await open();
      await page.getByLabel("PDF page", { exact: true }).selectOption("269");
      await expect(
        page.getByRole("heading", { name: /PDF page 269/ }),
      ).toBeVisible();
      expect(
        await page
          .getByRole("dialog")
          .evaluate((d) => d.scrollWidth <= d.clientWidth + 1),
      ).toBe(true);
      await page.getByLabel("Image zoom").selectOption("2");
      await expect(page.locator(".document-image-canvas")).toHaveAttribute(
        "style",
        /200%/,
      );
      await page.getByLabel("Image zoom").selectOption("1");
      await shot("mobile-page269");
      await page.locator(".document-image-scroll").scrollIntoViewIfNeeded();
      await expect(page.locator(".document-image-canvas>img")).toBeInViewport();
      await shot("mobile-source-image269");
      await page.locator('[data-block-id="p269-b1"]').scrollIntoViewIfNeeded();
      await expect(
        page.locator('[data-block-id="p269-b1"] pre'),
      ).toBeInViewport();
      await shot("mobile-source-block269");
      await close();
      const link = page.getByRole("link", {
        name: "Open cited original page",
        exact: true,
      });
      await link.scrollIntoViewIfNeeded();
      await expect(link).toBeInViewport();
      await link.click({ trial: true });
      const popupEvent = page.waitForEvent("popup");
      await link.click();
      const popup = await popupEvent;
      await popup.waitForLoadState();
      expect(popup.url()).toContain("version_id=edition-old#page=269");
      await expect(
        popup.getByRole("heading", {
          name: "UI-only synthetic original PDF endpoint",
        }),
      ).toBeVisible();
      await popup.close();
      await expect(page.locator(".document-citation blockquote")).toContainText(
        "Exact synthetic quote <table>literal</table>",
      );
      await shot("mobile-clickable-citation");
    },
  );
  expect(result.external).toEqual([]);
  expect(result.errors).toEqual([]);
  result.passed = true;
} catch (e) {
  result.passed = false;
  result.failure = String(e.stack || e);
  console.error(e);
  if (page)
    try {
      await shot("failure-" + Date.now());
    } catch {}
  process.exitCode = 1;
} finally {
  for (const release of held.splice(0)) release();
  if (context) {
    await context.close();
    result.cleanup.chromeClosed = true;
  }
  if (server) {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    result.cleanup.serverClosed = true;
  }
  result.checkCount = result.checks.length;
  await fs.writeFile(
    path.join(artifacts, "browser-run-" + Date.now() + ".json"),
    JSON.stringify(result, null, 2),
  );
  await fs.writeFile(
    path.join(artifacts, "browser-report.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify({
      passed: result.passed,
      checks: result.checkCount,
      cleanup: result.cleanup,
      report: path.join(artifacts, "browser-report.json"),
    }),
  );
}
