// Built React -> real HTTP fixture -> installed Chrome. Synthetic, never a live-service claim.
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { serveLearningFixture } from "./stage7-learning-fixture-http.mjs";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const artifacts = path.join(root, "artifacts/stage7-learning");
const scratch = await fs.mkdtemp(
  "C:/Users/17193/AppData/Local/hermes/cache/scratch/stage7-learning-owned-",
);
await fs.mkdir(path.join(artifacts, "screenshots"), { recursive: true });
const result = {
  label:
    "Built React, installed Chrome, labelled synthetic HTTP state only. No backend/SQLite/model/Tavily/production calls.",
  checks: [],
  screenshots: [],
  errors: [],
  external: [],
  http_errors: [],
  cleanup: {},
  scratch,
};
let browser, server, fixture, url, page;
const verify = async (name, fn) => {
  await fn();
  result.checks.push({ name, passed: true });
  console.log(`PASS ${name}`);
};
const screen = async (name) => {
  await page.mouse.move(1, 1);
  await page.screenshot({
    path: path.join(artifacts, `screenshots/${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  result.screenshots.push(`screenshots/${name}.png`);
};
const goto = async (view, extra = "") => {
  await page.goto(`${url}/?view=${view}${extra}`);
  await expect(page.locator(".loading")).toHaveCount(0);
};
const overflow = async () =>
  page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth + 1,
  );
const turns = () => fixture.logs.filter((r) => r.path.endsWith("/tutor/turn"));
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
        input: path.join(root, "tests/stage7-learning-harness.html"),
      },
    },
  });
  ({ server, fixture, url } = await serveLearningFixture(
    path.join(scratch, "built"),
  ));
  browser = await chromium.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
    acceptDownloads: true,
    serviceWorkers: "block",
  });
  await context.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== url && !["blob:", "data:"].includes(u.protocol)) {
      result.external.push(u.origin);
      return route.abort();
    }
    return route.continue();
  });
  page = await context.newPage();
  page.on("pageerror", (e) => result.errors.push(String(e)));
  page.on("console", (m) => {
    if (
      m.type() === "error" &&
      !/Failed to load resource: the server responded with a status of (403|503)/.test(
        m.text(),
      )
    )
      result.errors.push(m.text());
  });
  page.on("response", (r) => {
    if (r.status() >= 400)
      result.http_errors.push({
        path: new URL(r.url()).pathname,
        status: r.status(),
      });
  });
  await goto("home");
  await verify(
    "course Home actual statuses/counts, one primary per session, no fabricated progress",
    async () => {
      await expect(
        page.getByRole("heading", { name: "Course Home", exact: true }),
      ).toBeVisible();
      await expect(page.locator(".session-card-footer .primary")).toHaveCount(
        2,
      );
      await expect(page.locator(".course-management")).toContainText(
        "Published edition 3",
      );
      await expect(page.locator(".course-stats")).toContainText("12");
      await expect(page.getByRole("progressbar")).toHaveCount(0);
      expect(await overflow()).toBe(false);
    },
  );
  await screen("desktop-home");
  await verify(
    "keyboard course-library navigation activates real callback",
    async () => {
      const button = page.getByRole("button", {
        name: "Course materials",
        exact: true,
      });
      await button.focus();
      await page.keyboard.press("Enter");
      await expect(
        page.getByRole("heading", { name: "Course materials", exact: true }),
      ).toBeVisible();
      expect(
        await page.evaluate(() => window.learningFixture.events.at(-1)),
      ).toEqual({ action: "library", id: "fixture-course" });
    },
  );
  await verify(
    "canonical library shows real memberships/privacy and useful filters",
    async () => {
      await expect(page.locator(".library-item")).toHaveCount(3);
      await expect(
        page.locator(
          '[data-library-material="fixture-reading"] .library-memberships button',
        ),
      ).toHaveCount(2);
      await page
        .getByLabel("Visibility", { exact: true })
        .selectOption("teacher");
      await expect(page.locator(".library-item")).toHaveCount(1);
      await expect(page.locator(".material-visibility")).toContainText(
        "Teacher only",
      );
      await page.getByLabel("Visibility", { exact: true }).selectOption("");
      await page
        .getByLabel("Linked session", { exact: true })
        .selectOption("unlinked");
      await expect(page.locator(".library-item")).toHaveCount(1);
      await expect(page.locator(".library-memberships")).toContainText(
        "Not linked",
      );
      await page.getByLabel("Linked session", { exact: true }).selectOption("");
      await page.getByLabel("Find a material").fill("Assessment");
      await expect(page.locator(".library-result-count")).toHaveText(
        "Showing 1 of 3",
      );
      await page.getByLabel("Find a material").fill("");
    },
  );
  await screen("desktop-library");
  await verify(
    "library management routes to selected actual session, not an invented upload route",
    async () => {
      await page
        .getByLabel("Session", { exact: true })
        .selectOption("fixture-session-two");
      await page
        .getByRole("button", { name: "Manage in session" })
        .click();
      await expect(
        page.getByRole("heading", { name: "Session 2 materials", exact: true }),
      ).toBeVisible();
      expect(
        await page.evaluate(() => window.learningFixture.events.at(-1)),
      ).toEqual({ action: "manage-session", id: "fixture-session-two" });
      await page
        .getByLabel("Course Materials", { exact: true })
        .selectOption("fixture-unlinked");
      await page
        .getByRole("button", { name: "Add to this session", exact: true })
        .click();
      await expect(page.locator(".notice")).toContainText(
        "Draft saved and verified",
      );
      expect(
        fixture.data.materials.find((m) => m.id === "fixture-unlinked")
          .session_ids,
      ).toEqual(["fixture-session-two"]);
      const attach = fixture.logs.findIndex((l) =>
        l.path.endsWith("/materials/attach"),
      );
      expect(
        fixture.logs
          .slice(attach + 1)
          .filter((l) => l.method === "GET")
          .map((l) => l.path),
      ).toEqual(
        expect.arrayContaining([
          "/api/sessions/fixture-session-two",
          "/api/courses/fixture-course/materials",
        ]),
      );
    },
  );
  await verify(
    "material preview has real HTTP content, Escape restores launcher focus",
    async () => {
      const button = page
        .getByRole("button", { name: "Preview material", exact: true })
        .first();
      await button.click();
      await expect(page.locator(".preview-text")).toContainText(
        "Synthetic authenticated original material text",
      );
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(button).toBeFocused();
    },
  );
  await goto("materials");
  await verify(
    "material link draft navigation guard preserves edits, save reads both scopes",
    async () => {
      await page
        .getByLabel("URL / DOI", { exact: true })
        .fill("https://example.invalid/fixture");
      expect(
        await page.evaluate(() => window.learningFixture.hasUnsavedChanges()),
      ).toBe(true);
      page.once("dialog", (d) => d.dismiss());
      await page
        .getByRole("navigation", { name: "Fixture views" })
        .getByRole("button", { name: "home", exact: true })
        .click();
      await expect(page.getByLabel("URL / DOI", { exact: true })).toHaveValue(
        "https://example.invalid/fixture",
      );
      await page
        .getByRole("button", { name: "Save link", exact: true })
        .click();
      await expect(page.locator(".notice")).toContainText(
        "Draft saved and verified",
      );
      expect(
        await page.evaluate(() => window.learningFixture.hasUnsavedChanges()),
      ).toBe(false);
    },
  );
  await screen("desktop-material-editor");
  await goto("student");
  await verify(
    "reading-first student typography, visible question, accessible composer",
    async () => {
      await expect(
        page.getByRole("heading", {
          name: fixture.data.sessions[0].title,
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.locator(".guided-question h3")).toContainText(
        "intended use",
      );
      const styles = await page.evaluate(() => {
        const s = (selector) => {
          const c = getComputedStyle(document.querySelector(selector));
          return {
            font: c.fontFamily,
            size: parseFloat(c.fontSize),
            color: c.color,
            background: c.backgroundColor,
          };
        };
        return {
          title: s(".guided-heading h1"),
          reading: s(".guided-message-text"),
          helper: s(".guided-composer-caption small"),
          question: s(".guided-question h3"),
        };
      });
      expect(styles.title.font).toContain("Georgia");
      expect(styles.reading.font).toContain("Segoe UI");
      expect(styles.reading.size).toBeGreaterThanOrEqual(15);
      expect(styles.helper.size).toBeGreaterThanOrEqual(13);
      expect(styles.reading.color).toBe("rgb(35, 53, 46)");
      result.computed = styles;
      expect(await overflow()).toBe(false);
    },
  );
  await screen("desktop-student");
  await verify(
    "native Tab focus has semantic blue outline; Shift+Enter and composition do not send",
    async () => {
      const input = page.getByRole("textbox", { name: "Message your tutor" });
      await input.focus();
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => {
        const s = getComputedStyle(document.activeElement);
        return { color: s.outlineColor, width: s.outlineWidth };
      });
      expect(focused.color).toBe("rgb(53, 92, 152)");
      expect(parseFloat(focused.width)).toBeGreaterThanOrEqual(2);
      await input.fill("Line one");
      const count = turns().length;
      await page.keyboard.press("Shift+Enter");
      await expect(input).toHaveValue("Line one\n");
      expect(turns()).toHaveLength(count);
      await input.dispatchEvent("compositionstart");
      await page.keyboard.press("Enter");
      expect(turns()).toHaveLength(count);
      await input.dispatchEvent("compositionend");
    },
  );
  await verify(
    "failed turn saves raw message and retry reuses request id without duplicate",
    async () => {
      const input = page.getByRole("textbox", { name: "Message your tutor" });
      await input.fill("Synthetic reasoning preserved on failure.");
      fixture.failures = 1;
      await page.keyboard.press("Enter");
      await expect(page.locator(".error-banner")).toContainText(
        "Your response was saved",
      );
      await expect(input).toHaveValue(
        "Synthetic reasoning preserved on failure.",
      );
      const first = turns().at(-1).body;
      await page
        .getByRole("button", { name: "Retry previous message", exact: true })
        .click();
      await expect(page.locator(".guided-retry")).toHaveCount(0);
      await expect(input).toHaveValue("");
      expect(turns().at(-1).body.request_id).toBe(first.request_id);
      expect(first.web_search).toBe(false);
      expect(
        fixture.data.workspace.messages.filter(
          (m) => m.content === first.message,
        ),
      ).toHaveLength(1);
    },
  );
  await verify(
    "saved-response revision remains editable, example gate visible until submit",
    async () => {
      await page
        .getByRole("button", { name: "Saved responses", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Request instructor example",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(page.locator(".guided-reference")).toContainText(
        "Available after submitting",
      );
      await page
        .getByRole("textbox", { name: "Edit saved response" })
        .fill("Revised synthetic response stored by HTTP.");
      await page
        .getByRole("button", { name: "Save response", exact: true })
        .click();
      await expect(
        page.locator(".guided-saved-answer > small").first(),
      ).toContainText("Saved to your record");
      expect(fixture.data.workspace.attempts["fixture-question"].answer).toBe(
        "Revised synthetic response stored by HTTP.",
      );
      await page
        .getByRole("button", { name: "Submit for teacher review", exact: true })
        .click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Submit worksheet", exact: true })
        .click();
      await expect(page.locator(".guided-locked")).toContainText(
        "Submitted for teacher review",
      );
      await expect(
        page.getByRole("button", {
          name: "Request instructor example",
          exact: true,
        }),
      ).toBeEnabled();
      await page
        .getByRole("button", {
          name: "Request instructor example",
          exact: true,
        })
        .click();
      await expect(page.locator(".guided-reference")).toContainText(
        "Synthetic comparison",
      );
    },
  );
  await verify(
    "managed preview preserves preview_id on saved answers and tutor turns",
    async () => {
      const original = structuredClone(fixture.data.workspace);
      fixture.data.workspace.submission.status = "in_progress";
      fixture.data.workspace.version = {
        id: null,
        number: null,
        is_current: false,
        is_draft: true,
      };
      fixture.data.workspace.preview = {
        id: "fixture-preview-run",
        revision: "fixture-revision",
        current_revision: "fixture-revision",
        stale: false,
        reset_required: false,
        pending: false,
        bound_at: "2026-10-07T12:00:00Z",
      };
      await goto("preview");
      await page
        .getByRole("button", { name: "Saved responses", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Edit saved response" })
        .fill("Synthetic preview-run answer.");
      await page
        .getByRole("button", { name: "Save response", exact: true })
        .click();
      await expect(
        page.locator(".guided-saved-answer > small").first(),
      ).toContainText("Saved to your record");
      expect(
        fixture.logs
          .filter((l) => l.path.endsWith("/answers/fixture-question"))
          .at(-1).query,
      ).toContain("preview_id=fixture-preview-run");
      await page.getByRole("button", { name: "Close learning panel" }).click();
      await page
        .getByRole("textbox", { name: "Message your tutor" })
        .fill("Synthetic preview-run conversation.");
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(
        page.getByRole("textbox", { name: "Message your tutor" }),
      ).toHaveValue("");
      expect(turns().at(-1).body.preview_id).toBe("fixture-preview-run");
      fixture.data.workspace = original;
    },
  );
  await goto("record");
  await verify(
    "record facts collapsed; original reply and revision navigation intact",
    async () => {
      await expect(page.locator(".process-details[open]")).toHaveCount(0);
      await page
        .getByRole("button", { name: "Locate latest reply", exact: true })
        .click();
      await expect(
        page.locator('[data-message-id="fixture-original"]'),
      ).toBeFocused();
      await expect(
        page.locator(
          '[data-message-id="fixture-original"] .guided-message-text',
        ),
      ).toHaveText("I would check the score.\nThen ask what it represents.");
      await page
        .getByRole("button", { name: "Process overview", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Responses & revisions", exact: true })
        .click();
      await page.getByText("Earlier responses", { exact: true }).click();
      await expect(page.locator(".guided-revisions")).toContainText(
        "I would check the score.",
      );
      await expect(page.locator(".guided-reference")).toContainText(
        "Private instructor example",
      );
    },
  );
  await page
    .getByRole("button", { name: "Process overview", exact: true })
    .click();
  await screen("desktop-record");
  await verify(
    "record export is exact HTTP JSON with original raw messages",
    async () => {
      await page.getByLabel("Download conversation").click();
      const wait = page.waitForEvent("download");
      await page
        .getByRole("link", { name: "Full learning record · JSON", exact: true })
        .click();
      const download = await wait;
      const file = path.join(artifacts, "fixture-record-download.json");
      await download.saveAs(file);
      expect(JSON.parse(await fs.readFile(file, "utf8"))).toEqual(
        fixture.data.record,
      );
    },
  );
  await goto("authoring");
  await verify(
    "question editor keeps format/source/private answer/image controls reachable",
    async () => {
      await expect(
        page.getByRole("textbox", { name: "Question prompt", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("textbox", {
          name: "Private answer / example",
          exact: true,
        }),
      ).toBeVisible();
      await page.getByText("Response format & hints", { exact: true }).click();
      await expect(
        page.getByLabel("Non-answer hint", { exact: true }),
      ).toBeVisible();
      await page
        .getByText("Images & original provenance · 0 images", { exact: true })
        .click();
      await page
        .getByRole("button", { name: "Add image", exact: true })
        .click();
      await expect(
        page.getByLabel("Accessible description", { exact: true }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Remove image", exact: true })
        .click();
      const help = page.getByRole("button", {
        name: "question source scope",
        exact: true,
      });
      await help.focus();
      await expect(page.getByRole("tooltip")).toContainText(
        "does not make it public",
      );
      await page.keyboard.press("Escape");
      await expect(page.getByRole("tooltip")).toHaveCount(0);
    },
  );
  await screen("desktop-question-editor");
  await goto("import");
  await verify(
    "worksheet extraction still requires explicit review and draft-only save",
    async () => {
      await page.getByLabel("Worksheet file", { exact: true }).setInputFiles({
        name: "synthetic-fixture.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Synthetic worksheet. No real document content."),
      });
      await page
        .getByRole("button", { name: "Extract preview", exact: true })
        .click();
      await expect(page.locator(".material-warning")).toContainText(
        "no document or model was processed",
      );
      await expect(
        page.getByRole("button", { name: "Save reviewed draft", exact: true }),
      ).toBeDisabled();
      await page
        .getByLabel(
          "I reviewed the extracted questions, references and figures.",
          { exact: true },
        )
        .check();
      await page
        .getByRole("button", { name: "Save reviewed draft", exact: true })
        .click();
      await expect(page.locator(".notice")).toContainText("not published");
      expect(
        fixture.data.sessions[0].questions.some(
          (q) => q.id === "fixture-imported-question",
        ),
      ).toBe(true);
    },
  );
  await goto("history");
  await verify(
    "My Learning reads edition-pinned records and opens exact saved run",
    async () => {
      await expect(
        page.getByRole("heading", { name: "My Learning", exact: true }),
      ).toBeVisible();
      await expect(page.locator(".history-row")).toContainText("Edition 3");
      await expect(page.locator(".history-row")).toContainText(
        "1/1 responses saved",
      );
      await page.locator(".history-row").focus();
      await page.keyboard.press("Enter");
      expect(
        await page.evaluate(() => window.learningFixture.events.at(-1)),
      ).toEqual({ action: "history:fixture-edition", id: "fixture-session" });
    },
  );
  await screen("desktop-history");
  await verify(
    "library permission failure is informative, explicit refresh recovers",
    async () => {
      fixture.libraryError = true;
      await goto("library");
      await expect(page.locator(".error-banner")).toContainText(
        "only this course's owner",
      );
      await expect(page.locator(".library-item")).toHaveCount(0);
      fixture.libraryError = false;
      await page.getByRole("button", { name: "Refresh", exact: true }).click();
      await expect(page.locator(".library-item")).toHaveCount(4);
    },
  );
  fixture.data.workspace = JSON.parse(
    await fs.readFile(
      new URL("./stage7-learning-fixture.json", import.meta.url),
      "utf8",
    ),
  ).workspace;
  for (const view of ["home", "library", "student", "record"]) {
    await page.setViewportSize({ width: 390, height: 844 });
    await goto(view);
    await verify(
      `390px ${view}: no horizontal overflow, reachable controls`,
      async () => {
        expect(await overflow()).toBe(false);
        await expect(page.getByRole("heading").first()).toBeVisible();
      },
    );
    if (view === "student") {
      await page
        .getByRole("button", { name: "Saved responses", exact: true })
        .click();
      await expect(page.locator(".guided-drawer")).toBeVisible();
      await page.getByRole("button", { name: "Close learning panel" }).click();
      await verify(
        "390px composer and Send remain inside the shell and accept an actual click",
        async () => {
          const input = page.getByRole("textbox", {
            name: "Message your tutor",
          });
          await input.fill("Mobile synthetic response.");
          const send = page.getByRole("button", { name: "Send", exact: true });
          const button = await send.boundingBox();
          const shell = await page.locator(".guided-shell").boundingBox();
          expect(button.y + button.height).toBeLessThanOrEqual(
            shell.y + shell.height,
          );
          await send.click();
          await expect(input).toHaveValue("");
          expect(turns().at(-1).body.message).toBe(
            "Mobile synthetic response.",
          );
        },
      );
    }
    if (view === "record") {
      await verify(
        "390px record can locate the original and return to process facts",
        async () => {
          await page
            .getByRole("button", { name: "Locate latest reply", exact: true })
            .click();
          await expect(
            page.locator('[data-message-id="fixture-original"]'),
          ).toBeFocused();
          await page
            .getByRole("button", { name: "Process overview", exact: true })
            .click();
          await expect(page.locator(".process-heading h3")).toBeVisible();
        },
      );
    }
    await screen(`mobile-${view}`);
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  await goto("library");
  await verify(
    "200% CSS zoom retains labels and library actions without clipping",
    async () => {
      await page.evaluate(() => {
        document.body.style.zoom = "2";
      });
      expect(await overflow()).toBe(false);
      await expect(page.getByLabel("Find a material")).toBeVisible();
    },
  );
  await screen("zoom-library-200");
  expect(result.external).toEqual([]);
  expect(result.errors).toEqual([]);
  expect(result.http_errors).toEqual([
    { path: "/api/sessions/fixture-session/tutor/turn", status: 503 },
    { path: "/api/courses/fixture-course/materials", status: 403 },
  ]);
  result.passed = true;
} catch (e) {
  result.passed = false;
  result.failure = String(e.stack || e);
  if (page) await screen("failure").catch(() => {});
  throw e;
} finally {
  if (browser) {
    await browser.close();
    result.cleanup.browser_closed = true;
  }
  if (server) {
    await new Promise((r) => server.close(r));
    result.cleanup.server_closed = !server.listening;
  }
  result.http_logs = fixture?.logs;
  result.check_count = result.checks.length;
  result.screenshot_count = result.screenshots.length;
  await fs.writeFile(
    path.join(artifacts, "browser-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify({
      passed: result.passed,
      checks: result.check_count,
      screenshots: result.screenshot_count,
      artifacts,
      cleanup: result.cleanup,
    }),
  );
}
