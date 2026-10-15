// Built React + real local HTTP + installed Chrome. Labelled UI-only fixture.
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { serveFixture } from "./fixture-http.mjs";
const artifacts = path.dirname(fileURLToPath(import.meta.url)),
  root = path.resolve(artifacts, "../..");
const scratchRoot = "C:/Users/17193/AppData/Local/hermes/cache/scratch";
const scratch = await fs.mkdtemp(
  path.join(scratchRoot, "stage6-teacher-owned-"),
);
const screenshots = path.join(artifacts, "screenshots");
await fs.mkdir(screenshots, { recursive: true });
const checks = [],
  external = [],
  errors = [];
let context, server, url, fixture;
const result = {
  label: "Synthetic HTTP fixture; no backend/SQLite/model inference proof",
  checks,
  screenshots: [],
  external,
  errors,
  cleanup: {},
};
const verify = async (name, fn) => {
  await fn();
  checks.push({ name, passed: true });
  console.log(`PASS ${name}`);
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
try {
  await build({
    root,
    configFile: false,
    plugins: [react()],
    cacheDir: path.join(scratch, "vite-cache"),
    build: {
      outDir: path.join(scratch, "built"),
      emptyOutDir: true,
      rollupOptions: { input: path.join(artifacts, "index.html") },
    },
  });
  ({ server, url, fixture } = await serveFixture(path.join(scratch, "built")));
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
      external.push(u.href);
      await route.abort();
    } else await route.continue();
  });
  const page = context.pages()[0];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (
      m.type() === "error" &&
      !/Failed to load resource: the server responded with a status of (503|422)/.test(
        m.text(),
      )
    )
      errors.push(m.text());
  });
  const screen = async (name) => {
    await page.screenshot({
      path: path.join(screenshots, `${name}.png`),
      fullPage: false,
    });
    result.screenshots.push(`screenshots/${name}.png`);
  };
  const pane = page.getByRole("complementary", {
    name: "Saved draft test chat",
  });
  const composer = page.getByRole("textbox", { name: "Test response" });
  const title = page.getByRole("textbox", { name: "Title", exact: true });
  const additional = page.locator(".tf-additional textarea");
  const save = page.getByRole("button", {
    name: "Save content draft",
    exact: true,
  });
  const imports = page.getByRole("button", {
    name: "Review instruction file",
    exact: true,
  });
  const importDialog = page.getByRole("dialog", {
    name: "Review instruction file",
  });
  const reviewText = () =>
    importDialog.getByRole("textbox", {
      name: "Review and edit extracted instructions",
    });
  const chooseFile = () => importDialog.getByLabel("Choose instruction file");
  const upload = async (name, text) =>
    chooseFile().setInputFiles({
      name,
      mimeType: "text/plain",
      buffer: Buffer.from(text),
    });
  const modelCalls = () =>
    fixture.logs.filter((l) => /tutor\/(start|turn)$/.test(l.path));
  await page.goto(url);
  await verify(
    "opening same-screen preview makes zero inference/reset writes",
    async () => {
      await expect(
        pane.getByRole("button", { name: "Start preview", exact: true }),
      ).toBeEnabled();
      expect(modelCalls()).toHaveLength(0);
      expect(
        fixture.logs.filter((l) => l.path.endsWith("preview/reset")),
      ).toHaveLength(0);
      await expect(composer).toBeDisabled();
    },
  );
  await screen("desktop-workbench");
  await verify(
    "real keyboard Start; unsaved configuration is not silently saved",
    async () => {
      await title.fill("Unsaved unrelated title");
      await expect(page.locator(".tw-unsaved-banner")).toContainText(
        "not these edits",
      );
      const start = pane.getByRole("button", {
        name: "Start preview",
        exact: true,
      });
      await start.focus();
      await page.keyboard.press("Enter");
      await expect(composer).toBeEnabled();
      expect(fixture.sessions.get("fixture-s1").title).not.toBe(
        "Unsaved unrelated title",
      );
      expect(modelCalls().filter((l) => l.path.endsWith("start"))).toHaveLength(
        1,
      );
      await expect(pane.locator(".tw-identity")).toContainText(
        "fixture-preview",
      );
      await expect(
        pane.getByRole("button", { name: /Submit|Confirm completion/ }),
      ).toHaveCount(0);
    },
  );
  await verify(
    "Shift+Enter newline and IME confirmation do not send",
    async () => {
      await composer.focus();
      await page.keyboard.type("Keyboard line one");
      await page.keyboard.press("Shift+Enter");
      await page.keyboard.type("line two");
      await expect(composer).toHaveValue("Keyboard line one\nline two");
      expect(modelCalls().filter((l) => l.path.endsWith("turn"))).toHaveLength(
        0,
      );
      await composer.dispatchEvent("compositionstart");
      await page.keyboard.press("Enter");
      expect(modelCalls().filter((l) => l.path.endsWith("turn"))).toHaveLength(
        0,
      );
      await composer.dispatchEvent("compositionend");
    },
  );
  await verify(
    "inflight preview blocks Save and Reset; Enter commits and same-ID ack clears draft",
    async () => {
      const typed = await composer.inputValue();
      fixture.control.turnDelay = 250;
      await page.keyboard.press("Enter");
      await expect(save).toBeDisabled();
      await expect(
        pane.getByRole("button", { name: "Reset my preview", exact: true }),
      ).toBeDisabled();
      await expect(composer).toBeEnabled();
      await expect(composer).toHaveValue("");
      await expect(save).toBeEnabled();
      expect(
        fixture
          .workspace("fixture-s1")
          .messages.filter((m) => m.role === "user")[0].content,
      ).toBe(typed);
      fixture.control.turnDelay = 0;
    },
  );
  await screen("desktop-started-preview");
  await verify(
    "HTTP failure keeps raw text and request ID; wrong completed ID does not ack",
    async () => {
      fixture.control.turnFail = 1;
      fixture.control.completedWrong = true;
      await composer.fill("Preserve failed text");
      await composer.press("Enter");
      await expect(
        pane.getByRole("button", {
          name: "Retry previous message",
          exact: true,
        }),
      ).toBeEnabled();
      await expect(composer).toHaveValue("Preserve failed text");
      const first = modelCalls()
        .filter((l) => l.path.endsWith("turn"))
        .at(-1).body;
      await pane
        .getByRole("button", { name: "Retry previous message", exact: true })
        .click();
      await expect(composer).toHaveValue("");
      const last = modelCalls()
        .filter((l) => l.path.endsWith("turn"))
        .at(-1).body;
      expect(last.request_id).toBe(first.request_id);
      expect(last.preview_id).toBe(first.preview_id);
      fixture.control.completedWrong = false;
    },
  );
  await verify(
    "save changed draft makes old chat stale and reset confirmation is cancellable",
    async () => {
      await composer.fill("Old generation unsent text");
      await save.click();
      await expect(
        pane.getByText(/This conversation uses an older saved draft/),
      ).toBeVisible();
      await expect(composer).toBeDisabled();
      await expect(pane.locator(".guided-message")).toHaveCount(5);
      await pane
        .getByRole("button", { name: "Reset my preview", exact: true })
        .click();
      await expect(
        page.getByRole("dialog", { name: "Reset your draft test?" }),
      ).toBeVisible();
      const before = fixture.workspace("fixture-s1").preview.id;
      await page.keyboard.press("Escape");
      expect(fixture.workspace("fixture-s1").preview.id).toBe(before);
    },
  );
  await screen("desktop-stale-preview");
  await verify(
    "confirmed reset changes generation; old browser text/retry never reused",
    async () => {
      const old = fixture.workspace("fixture-s1").preview.id;
      await pane
        .getByRole("button", { name: "Reset my preview", exact: true })
        .click();
      const confirm = page.getByRole("button", {
        name: "Confirm reset my preview",
        exact: true,
      });
      await confirm.focus();
      await page.keyboard.press("Enter");
      await expect(
        pane.getByText(/This conversation uses an older saved draft/),
      ).toHaveCount(0);
      await expect(
        pane.getByRole("button", { name: "Start preview", exact: true }),
      ).toBeEnabled();
      expect(fixture.workspace("fixture-s1").preview.id).not.toBe(old);
      await expect(composer).toHaveValue("");
      expect(fixture.workspace("fixture-s1").messages).toHaveLength(0);
      await pane
        .getByRole("button", { name: "Start preview", exact: true })
        .click();
      await expect(composer).toBeEnabled();
      await expect(
        pane.getByRole("button", {
          name: "Retry previous message",
          exact: true,
        }),
      ).toHaveCount(0);
    },
  );
  const source = page.locator(".tw-source");
  const beforeSource = modelCalls().length;
  await verify(
    "owner source review shows exact snippets, IDs, private reference, exclusion and coverage",
    async () => {
      await page
        .getByRole("combobox", { name: "Source review question" })
        .selectOption("q1");
      await page
        .getByRole("button", { name: "Review selected sources", exact: true })
        .click();
      await expect(source.locator(".tw-source-result")).toBeVisible();
      await expect(source).toContainText("answer key excluded");
      await expect(source).toContainText("not selected");
      await source
        .getByText("Current instructor reference · teacher-only", {
          exact: true,
        })
        .scrollIntoViewIfNeeded();
      expect(
        await source.locator(".tw-exact-text").allTextContents(),
      ).toContain("Exact private reference.\n  Preserve indentation.");
      const dup = source.getByText(/Duplicate source label · public-/);
      expect(await dup.count()).toBe(2);
      await source
        .locator("details")
        .filter({ hasText: "public-a" })
        .first()
        .locator("summary")
        .click();
      expect(
        await source.locator(".tw-exact-text").allTextContents(),
      ).toContain("Exact evidence from public-a.\nKeep spacing.");
      await source.locator(".tw-extraction").first().locator("summary").click();
      await expect(source).toContainText("Processed 1 of 2 parts");
      expect(modelCalls()).toHaveLength(beforeSource);
    },
  );
  await source.scrollIntoViewIfNeeded();
  await screen("desktop-source-review");
  await verify(
    "source inputs invalidate old compilation; late response cannot clobber fresh typing",
    async () => {
      fixture.control.sourceDelay = 220;
      await page
        .getByRole("combobox", { name: "Source review phase" })
        .selectOption("reading");
      await expect(source.locator(".tw-source-result")).toHaveCount(0);
      await page
        .getByRole("button", { name: "Review selected sources", exact: true })
        .click();
      await additional.fill("Fresh unsaved instruction overlay");
      await pause(260);
      await expect(source.locator(".tw-source-result")).toHaveCount(0);
      await expect(additional).toHaveValue("Fresh unsaved instruction overlay");
      fixture.control.sourceDelay = 0;
      await page
        .getByRole("checkbox", { name: /Use unsaved instruction overlay/ })
        .check();
      await page
        .getByRole("button", { name: "Review selected sources", exact: true })
        .click();
      await expect(source.locator(".tw-source-result")).toBeVisible();
      await expect(source).toContainText(
        "optional phase excludes private material",
      );
      await expect(source).toContainText("No current private reference");
      const last = fixture.logs
        .filter((l) => l.path.endsWith("source-review"))
        .at(-1).body;
      expect(last.instructions).toBe("Fresh unsaved instruction overlay");
    },
  );
  await verify(
    "real multipart instruction preview; explicit append marks only local draft dirty",
    async () => {
      await title.fill("Keep unrelated dirty field");
      const patches = fixture.logs.filter((l) => l.method === "PATCH").length;
      await imports.click();
      await upload("instructions.txt", "Imported reviewed text.");
      await expect(reviewText()).toHaveValue("Imported reviewed text.");
      await expect(importDialog).toContainText("OCR/partial");
      await importDialog.locator(".tw-extraction summary").click();
      await expect(importDialog).toContainText(
        "Fixture second page not extracted",
      );
      await screen("desktop-instruction-import");
      await importDialog
        .getByRole("button", { name: "Apply to unsaved draft", exact: true })
        .scrollIntoViewIfNeeded();
      await screen("desktop-instruction-confirmation");
      await importDialog
        .getByRole("button", { name: "Apply to unsaved draft", exact: true })
        .click();
      await expect(additional).toHaveValue(
        "Fresh unsaved instruction overlay\n\nImported reviewed text.",
      );
      await expect(title).toHaveValue("Keep unrelated dirty field");
      expect(fixture.logs.filter((l) => l.method === "PATCH").length).toBe(
        patches,
      );
      expect(
        fixture.logs
          .filter((l) => l.path.endsWith("instruction-import/preview"))
          .at(-1).multipart,
      ).toBe(true);
    },
  );
  await verify(
    "late extraction preserves review typing; cancellation and HTTP parser error preserve teacher edits",
    async () => {
      await imports.click();
      fixture.control.importDelay = 200;
      await upload("late.txt", "Late extraction text");
      await reviewText().fill("Newer review typing");
      await expect(
        importDialog.getByText(/your newer review edits were kept/),
      ).toBeVisible();
      await expect(reviewText()).toHaveValue("Newer review typing");
      await importDialog
        .getByRole("button", { name: /Cancel — keep draft unchanged/ })
        .click();
      await expect(additional).toHaveValue(
        "Fresh unsaved instruction overlay\n\nImported reviewed text.",
      );
      await imports.click();
      await expect(reviewText()).toHaveValue("Newer review typing");
      await upload("cancel-late.txt", "Cancelled late response");
      await page.keyboard.press("Escape");
      await imports.click();
      await pause(240);
      await expect(reviewText()).toHaveValue("Newer review typing");
      fixture.control.importDelay = 0;
      await upload("error.txt", "Invalid fixture");
      await expect(importDialog.getByRole("alert")).toContainText(
        "Deliberate parser HTTP failure",
      );
      await expect(reviewText()).toHaveValue("Newer review typing");
      await expect(title).toHaveValue("Keep unrelated dirty field");
    },
  );
  await verify(
    "combined 30000 limit blocks Apply without truncation; reviewed Replace is explicit",
    async () => {
      await upload("over-limit.txt", "x".repeat(30010));
      await expect(reviewText()).toHaveValue("x".repeat(30010));
      await expect(
        importDialog.getByRole("button", {
          name: "Apply to unsaved draft",
          exact: true,
        }),
      ).toBeDisabled();
      await reviewText().fill("x".repeat(30000));
      await expect(
        importDialog.getByRole("button", {
          name: "Apply to unsaved draft",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(reviewText()).toHaveValue("x".repeat(30000));
      await expect(importDialog).toContainText("nothing is silently truncated");
      await importDialog
        .getByRole("radio", {
          name: "Replace Additional instructions",
          exact: true,
        })
        .check();
      await expect(
        importDialog.getByRole("button", {
          name: "Apply to unsaved draft",
          exact: true,
        }),
      ).toBeEnabled();
      await reviewText().fill("Explicit replacement");
      await importDialog
        .getByRole("button", { name: "Apply to unsaved draft", exact: true })
        .click();
      await expect(additional).toHaveValue("Explicit replacement");
      await expect(title).toHaveValue("Keep unrelated dirty field");
    },
  );
  await verify(
    "availability save preserves unrelated unsaved teacher fields and preview identity",
    async () => {
      const id = fixture.workspace("fixture-s1").preview.id;
      await page
        .getByRole("button", { name: "Apply availability now", exact: true })
        .click();
      await expect(
        page.getByText("Availability saved", { exact: false }),
      ).toBeVisible();
      await expect(title).toHaveValue("Keep unrelated dirty field");
      await expect(additional).toHaveValue("Explicit replacement");
      await expect(page.locator(".tw-unsaved-banner")).toBeVisible();
      expect(fixture.workspace("fixture-s1").preview.id).toBe(id);
      expect(fixture.workspace("fixture-s1").preview.stale).toBe(false);
    },
  );
  await verify(
    "closing and reopening pane does not navigate, save or call model",
    async () => {
      const count = modelCalls().length;
      await pane.getByRole("button", { name: "Close test chat" }).click();
      await expect(pane).toBeHidden();
      await page
        .getByRole("button", { name: "Test saved draft", exact: true })
        .click();
      await expect(pane).toBeVisible();
      expect(modelCalls()).toHaveLength(count);
      expect(
        await page.locator("body").getAttribute("data-full-preview"),
      ).toBeNull();
    },
  );
  await verify(
    "390px stacked editor and preview remain reachable without horizontal overflow",
    async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await title.scrollIntoViewIfNeeded();
      await screen("mobile-editor");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page
        .getByRole("button", { name: "Test saved draft", exact: true })
        .click();
      await expect(pane).toBeVisible();
      await composer.scrollIntoViewIfNeeded();
      await screen("mobile-preview");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await composer.focus();
      await page.keyboard.type("Mobile keyboard");
      await page.keyboard.press("Shift+Enter");
      await page.keyboard.type("newline");
      await expect(composer).toHaveValue("Mobile keyboard\nnewline");
      await page.keyboard.press("Tab");
      expect(
        await page.evaluate(() => document.activeElement?.textContent),
      ).toContain("Send");
      await pane.getByRole("link", { name: "Back to configuration" }).click();
      await title.fill("Mobile edit retained");
      await expect(title).toHaveValue("Mobile edit retained");
    },
  );
  await verify(
    "390px import confirmation and keyboard Escape preserve local edits",
    async () => {
      const before = await additional.inputValue();
      await imports.click();
      await importDialog
        .getByRole("button", { name: "Apply to unsaved draft", exact: true })
        .scrollIntoViewIfNeeded();
      await screen("mobile-instruction-confirmation");
      const box = await importDialog.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(390);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.keyboard.press("Tab");
      expect(
        await page.evaluate(() => !!document.activeElement?.closest("dialog")),
      ).toBe(true);
      await page.keyboard.press("Escape");
      await expect(importDialog).toHaveCount(0);
      await expect(additional).toHaveValue(before);
    },
  );
  await verify(
    "late old-session GET cannot replace new teacher session or preview",
    async () => {
      fixture.control.sessionDelay = 200;
      fixture.control.workspaceDelay = 200;
      await page
        .getByRole("button", { name: "Switch fixture session" })
        .click();
      await pause(30);
      fixture.control.sessionDelay = 0;
      fixture.control.workspaceDelay = 0;
      await page
        .getByRole("button", { name: "Switch fixture session" })
        .click();
      await expect(page.getByTestId("fixture-session")).toHaveText(
        "fixture-s1",
      );
      await expect(title).toHaveValue("Unsaved unrelated title");
      await pause(240);
      await expect(title).toHaveValue("Unsaved unrelated title");
      expect(await page.getByTestId("fixture-session").textContent()).toBe(
        "fixture-s1",
      );
    },
  );
  await verify(
    "late old-preview workspace response cannot replace freshly opened session",
    async () => {
      fixture.control.workspaceDelay = 250;
      await page
        .getByRole("button", { name: "Switch fixture session" })
        .click();
      await expect(title).toHaveValue("Teaching design fixture-s2");
      await expect
        .poll(
          () =>
            fixture.logs.filter(
              (l) => l.path === "/api/sessions/fixture-s2/workspace",
            ).length,
        )
        .toBeGreaterThan(0);
      fixture.control.workspaceDelay = 0;
      await page
        .getByRole("button", { name: "Switch fixture session" })
        .click();
      await expect(title).toHaveValue("Unsaved unrelated title");
      await expect(pane.locator(".tw-identity")).toContainText(
        fixture.workspace("fixture-s1").preview.id,
      );
      await pause(280);
      await expect(title).toHaveValue("Unsaved unrelated title");
      await expect(pane.locator(".tw-identity")).toContainText(
        fixture.workspace("fixture-s1").preview.id,
      );
    },
  );
  await verify(
    "no unexpected browser errors, no external requests, no publish/student writes",
    async () => {
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
      expect(
        fixture.logs.some((l) =>
          /publish|students|submit|settings|\/chat$/.test(l.path),
        ),
      ).toBe(false);
    },
  );
  result.http = fixture.snapshot();
  result.passed = true;
} catch (e) {
  result.passed = false;
  result.failure = String(e.stack || e);
  console.error(e);
  process.exitCode = 1;
  if (context)
    try {
      await context
        .pages()[0]
        .screenshot({
          path: path.join(screenshots, "failure.png"),
          fullPage: false,
        });
      result.screenshots.push("screenshots/failure.png");
    } catch {}
  if (fixture) result.http = fixture.snapshot();
} finally {
  if (context) {
    await context.close();
    result.cleanup.browserClosed = true;
  }
  if (server) {
    await new Promise((resolve) => server.close(resolve));
    result.cleanup.serverClosed = true;
    try {
      await fetch(url);
      result.cleanup.portClosed = false;
    } catch {
      result.cleanup.portClosed = true;
    }
  }
  await fs.rm(scratch, { recursive: true, force: true });
  result.cleanup.scratchRemoved = true;
  await fs.writeFile(
    path.join(artifacts, "browser-results.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify(
      {
        passed: result.passed,
        checks: checks.length,
        screenshots: result.screenshots,
        errors,
        external,
        cleanup: result.cleanup,
      },
      null,
      2,
    ),
  );
}
