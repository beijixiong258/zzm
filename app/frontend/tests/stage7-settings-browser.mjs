// Actual installed Chrome + built React + synthetic local HTTP fixture.
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { serveSettingsFixture } from "./stage7-settings-fixture-http.mjs";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const artifacts = path.join(root, "artifacts/stage7-settings"),
  screenshots = path.join(artifacts, "screenshots");
const scratch = await fs.mkdtemp(
  "C:/Users/17193/AppData/Local/hermes/cache/scratch/stage7-settings-owned-",
);
await fs.mkdir(screenshots, { recursive: true });
const result = {
  label:
    "Built React / real Chrome / synthetic HTTP fixture only. No backend, SQLite, real model, Tavily or credentials.",
  checks: [],
  screenshots: [],
  errors: [],
  external: [],
  responses: [],
  cleanup: {},
};
let browser, server, fixture, url, page;
const verify = async (name, fn) => {
  await fn();
  result.checks.push({ name, passed: true });
  console.log(`PASS ${name}`);
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const probes = () => fixture.logs.filter((l) => l.path.endsWith("/test"));
const goto = async (section = "model", role = "admin") => {
  await page.goto(`${url}/?section=${section}&role=${role}`);
  await expect(page.locator(".loading")).toHaveCount(0);
};
const screen = async (name) => {
  await page.mouse.move(2, 2);
  await page.screenshot({
    path: path.join(screenshots, `${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  result.screenshots.push(`screenshots/${name}.png`);
};
const save = () =>
  page.getByRole("button", { name: "Save changes", exact: true });
const key = () => page.getByLabel("API key", { exact: true });
const check = () => page.locator(".settings-check");
const nav = (label) =>
  page
    .getByRole("navigation", { name: "Settings sections" })
    .getByRole("button", { name: label, exact: true });
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
        input: path.join(root, "tests/stage7-settings-harness.html"),
      },
    },
  });
  ({ fixture, server, url } = await serveSettingsFixture(
    path.join(scratch, "built"),
  ));
  browser = await chromium.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1000 },
    serviceWorkers: "block",
  });
  await context.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.origin !== url && !["data:", "blob:"].includes(u.protocol)) {
      result.external.push(u.origin);
      return route.abort();
    }
    return route.continue();
  });
  page = await context.newPage();
  page.on("pageerror", (e) => result.errors.push(String(e)));
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !/^Failed to load resource: the server responded with a status of (503|422)/.test(
        message.text(),
      )
    )
      result.errors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400)
      result.responses.push({
        path: new URL(response.url()).pathname,
        status: response.status(),
      });
  });
  await goto();
  await verify(
    "mount reads configuration only, no demo selector or automatic test",
    async () => {
      await expect(page.getByLabel("Model name")).toHaveValue(
        "Fixture teaching model",
      );
      await expect(check()).toHaveText("Not checked");
      expect(probes()).toHaveLength(0);
      await expect(page.locator(".mode-choices")).toHaveCount(0);
      expect(await page.locator(".settings-content").innerText()).not.toMatch(
        /demo|Feedback mode/i,
      );
      await expect(key()).toHaveValue("");
      await expect(save()).toBeDisabled();
    },
  );
  await screen("desktop-model-not-checked");
  await verify(
    "computed type hierarchy and semantic colors follow calibrated tokens",
    async () => {
      const style = await page.evaluate(() => {
        const css = (selector) => {
          const s = getComputedStyle(document.querySelector(selector));
          return {
            font: s.fontFamily,
            size: parseFloat(s.fontSize),
            color: s.color,
            background: s.backgroundColor,
          };
        };
        return {
          title: css(".settings-page-heading h1"),
          field: css("#settings-model-name"),
          helper: css(".settings-helper"),
          paper: css(".settings-service"),
          selected: css(".settings-local-nav .selected"),
          blue: css(".settings-check"),
        };
      });
      expect(style.title.font).toContain("Georgia");
      expect(style.title.size).toBe(32);
      expect(style.field.font).toContain("Segoe UI");
      expect(style.field.size).toBe(15);
      expect(style.helper.size).toBe(13);
      expect(style.paper.background).toBe("rgb(255, 255, 255)");
      expect(style.blue.color).toBe("rgb(53, 92, 152)");
      result.computed_styles = style;
    },
  );
  await verify("keyboard focus and Help Escape work", async () => {
    const help = page.getByRole("button", { name: "Help with model API key" });
    await help.focus();
    await expect(page.getByRole("tooltip")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    const focus = await help.evaluate((el) => ({
      color: getComputedStyle(el).outlineColor,
      width: getComputedStyle(el).outlineWidth,
    }));
    expect(focus.width).toBe("3px");
  });
  await verify(
    "explicit keyboard test reads persisted last check",
    async () => {
      const test = page.getByRole("button", { name: "Test connection" });
      await test.focus();
      await page.keyboard.press("Enter");
      await expect(check()).toHaveText("Last test succeeded");
      await expect(page.locator(".settings-connection")).toContainText(
        "Last checked:",
      );
      expect(probes()).toHaveLength(1);
    },
  );
  await screen("desktop-model-last-success");
  await verify(
    "dirty edits invalidate old green; navigation cancellation keeps edits",
    async () => {
      await page.getByLabel("Model name").fill("Edited fixture model");
      await expect(check()).toHaveText("Not checked");
      await expect(
        page.getByRole("button", { name: "Test connection" }),
      ).toBeDisabled();
      page.once("dialog", (d) => d.dismiss());
      await nav("Web Search").click();
      await expect(page.getByLabel("Model name")).toHaveValue(
        "Edited fixture model",
      );
      expect(
        await page.evaluate(() => window.settingsFixture.hasUnsavedChanges()),
      ).toBe(true);
    },
  );
  await screen("desktop-model-dirty");
  await verify(
    "model save always openai, blank keeps key, separate GET clears dirty",
    async () => {
      await save().focus();
      await page.keyboard.press("Enter");
      await expect(
        page
          .getByRole("status")
          .filter({ hasText: "Changes saved and verified." }),
      ).toBeVisible();
      const write = fixture.logs.filter((l) => l.method === "PUT").at(-1);
      expect(write.mode).toBe("openai");
      expect(write.has_key).toBe(false);
      expect(fixture.model.ai.model).toBe("Edited fixture model");
      await expect(save()).toBeDisabled();
      expect(probes()).toHaveLength(1);
      const i = fixture.logs.indexOf(write);
      expect(fixture.logs[i + 1].method).toBe("GET");
      expect(fixture.logs[i + 1].path).toBe(write.path);
    },
  );
  await verify(
    "model explicit clear and replacement clear input only after readback",
    async () => {
      await page.getByLabel("Clear the current key on save").check();
      await expect(key()).toBeDisabled();
      await save().click();
      await expect(page.locator("#model-key-state")).toHaveText(
        "No key is configured.",
      );
      expect(
        fixture.logs.filter((l) => l.method === "PUT").at(-1).clear_key,
      ).toBe(true);
      await key().fill("synthetic-no-credential");
      await save().click();
      await expect(page.locator("#model-key-state")).toHaveText(
        "A key is configured.",
      );
      await expect(key()).toHaveValue("");
      expect(
        fixture.logs.filter((l) => l.method === "PUT").at(-1).has_key,
      ).toBe(true);
    },
  );
  await verify(
    "failed model test still refreshes persisted failure",
    async () => {
      fixture.modelTestFail = true;
      await page.getByRole("button", { name: "Test connection" }).click();
      await expect(check()).toHaveText("Connection issue");
      await expect(page.getByRole("alert")).toContainText(
        "Synthetic provider failure",
      );
    },
  );
  await screen("desktop-model-error");
  await verify(
    "failed model readback and mismatched readback retain dirty form",
    async () => {
      await page.getByLabel("Model name").fill("Retained draft");
      fixture.modelReadFail = 1;
      await save().click();
      await expect(page.getByRole("alert")).toContainText(
        "Save could not be verified",
      );
      await expect(page.getByLabel("Model name")).toHaveValue("Retained draft");
      await expect(save()).toBeEnabled();
      fixture.mismatchModel = true;
      await save().click();
      await expect(page.getByRole("alert")).toContainText("do not match");
      await expect(page.getByLabel("Model name")).toHaveValue("Retained draft");
      fixture.mismatchModel = false;
      await save().click();
      await expect(save()).toBeDisabled();
    },
  );
  await verify(
    "pending mutation disables fields and duplicate submission",
    async () => {
      fixture.modelDelayWrite = 250;
      await page.getByLabel("Model name").fill("Pending fixture model");
      await save().click();
      await expect(page.getByLabel("Model name")).toBeDisabled();
      await expect(
        page.getByRole("button", { name: "Saving…" }),
      ).toBeDisabled();
      await expect(save()).toBeDisabled();
      await expect(page.getByLabel("Model name")).toBeEnabled();
      fixture.modelDelayWrite = 0;
    },
  );
  await verify(
    "test readback failure hides old success; status refresh has no probe",
    async () => {
      fixture.modelTestFail = false;
      fixture.modelReadFail = 1;
      await page.getByRole("button", { name: "Test connection" }).click();
      await expect(check()).toHaveText("Status unavailable");
      const n = probes().length;
      await page.getByRole("button", { name: "Refresh saved status" }).click();
      await expect(check()).toHaveText("Last test succeeded");
      expect(probes()).toHaveLength(n);
    },
  );
  await nav("Web Search").click();
  await expect(page.getByLabel("Allow web search")).toBeChecked();
  await verify(
    "search opening shows environment key with zero automatic tests",
    async () => {
      await expect(page.locator("#search-key-state")).toHaveText(
        "Using an environment key.",
      );
      await expect(check()).toHaveText("Not checked");
    },
  );
  await screen("desktop-search-environment");
  await verify(
    "search blank keeps key and enable toggle requires save",
    async () => {
      const n = probes().length;
      await page.getByLabel("Allow web search").uncheck();
      await expect(
        page.getByRole("button", { name: "Test search" }),
      ).toBeDisabled();
      await save().click();
      await expect(save()).toBeDisabled();
      const write = fixture.logs.filter((l) => l.method === "PUT").at(-1);
      expect(write.enabled).toBe(false);
      expect(write.has_key).toBe(false);
      expect(write.clear_key).toBe(false);
      expect(fixture.search.api_key_source).toBe("environment");
      expect(probes()).toHaveLength(n);
    },
  );
  await screen("desktop-search-disabled");
  await verify(
    "explicit search clear suppresses environment; replacement gets server readback",
    async () => {
      await page.getByLabel("Clear the current key on save").check();
      await screen("desktop-search-clear-warning");
      await save().click();
      await expect(page.locator("#search-key-state")).toHaveText(
        "No key is configured.",
      );
      expect(fixture.search.api_key_source).toBe("none");
      const write = fixture.logs.filter((l) => l.method === "PUT").at(-1);
      expect(write.fields).toEqual(["enabled", "clear_api_key"]);
      await page.getByLabel("Allow web search").check();
      await key().fill("synthetic-no-credential");
      await save().click();
      await expect(save()).toBeDisabled();
      await expect(page.locator("#search-key-state")).toHaveText(
        "A key is saved.",
      );
      await expect(key()).toHaveValue("");
    },
  );
  await verify(
    "search keyboard explicit test; error persists last check",
    async () => {
      const button = page.getByRole("button", { name: "Test search" });
      await button.focus();
      await page.keyboard.press("Enter");
      await expect(check()).toHaveText("Last test succeeded");
      fixture.searchTestFail = true;
      await button.click();
      await expect(check()).toHaveText("Connection issue");
      await expect(page.getByRole("alert")).toContainText(
        "Synthetic provider failure",
      );
    },
  );
  await screen("desktop-search-error");
  await verify(
    "search rejected write, failed readback, divergent readback retain edits",
    async () => {
      await page.getByLabel("Allow web search").uncheck();
      fixture.searchWriteFail = true;
      await save().click();
      await expect(page.getByRole("alert")).toContainText(
        "rejected configuration",
      );
      await expect(page.getByLabel("Allow web search")).not.toBeChecked();
      await expect(save()).toBeEnabled();
      fixture.searchWriteFail = false;
      fixture.searchReadFail = 1;
      await save().click();
      await expect(page.getByRole("alert")).toContainText(
        "Save could not be verified",
      );
      await expect(save()).toBeEnabled();
      fixture.mismatchSearch = true;
      await save().click();
      await expect(page.getByRole("alert")).toContainText("do not match");
      await expect(save()).toBeEnabled();
      fixture.mismatchSearch = false;
      await save().click();
      await expect(save()).toBeDisabled();
    },
  );
  await verify(
    "no submitted keys or form data persist in browser storage",
    async () => {
      expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
      expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual(
        [],
      );
      expect(result.external).toEqual([]);
    },
  );
  await nav("Account").click();
  await expect(page.getByLabel("Full name")).toHaveValue("Alex Fixture");
  await screen("desktop-account");
  await verify(
    "real account name save uses independent authenticated readback",
    async () => {
      const name = page.getByLabel("Full name");
      await name.fill("Updated Fixture");
      page.once("dialog", (d) => d.dismiss());
      await page.getByRole("link", { name: "Fixture: leave settings" }).click();
      await expect(name).toHaveValue("Updated Fixture");
      const form = name.locator("xpath=ancestor::form");
      await form.getByRole("button", { name: "Save" }).click();
      await expect(page.locator(".notice")).toBeVisible();
      expect(fixture.user.name).toBe("Updated Fixture");
      expect(fixture.logs.at(-1).path).toBe("/api/auth/me");
      expect(
        await page.evaluate(() => window.settingsFixture.hasUnsavedChanges()),
      ).toBe(false);
    },
  );
  await nav("User Management").click();
  await expect(page.getByText("No eligible teachers.")).toBeVisible();
  await verify(
    "admin user management mounts existing real administration component",
    async () => {
      expect(fixture.logs.some((l) => l.path === "/api/admin/teachers")).toBe(
        true,
      );
      expect(fixture.logs.some((l) => l.path === "/api/admin/students")).toBe(
        true,
      );
    },
  );
  await verify(
    "direct unauthorized routes never mount/fetch privileged sections",
    async () => {
      for (const role of ["teacher", "student"])
        for (const section of ["model", "search", "users"]) {
          const start = fixture.logs.length;
          await goto(section, role);
          await expect(page.getByLabel("Full name")).toBeVisible();
          await expect(nav("AI Model")).toHaveCount(0);
          expect(
            fixture.logs
              .slice(start)
              .filter(
                (l) =>
                  l.path.startsWith("/api/teacher/") ||
                  l.path.startsWith("/api/admin/"),
              ),
          ).toHaveLength(0);
        }
    },
  );
  await screen("desktop-student-account-only");
  await verify(
    "late response after section switch cannot overwrite active section or update AI",
    async () => {
      fixture.reset();
      fixture.delayModelRead = 300;
      await page.goto(`${url}/?section=model`);
      await expect(page.locator(".loading")).toBeVisible();
      await nav("Web Search").click();
      await expect(page.getByLabel("Allow web search")).toBeVisible();
      await pause(350);
      await expect(page.getByLabel("Model name")).toHaveCount(0);
      await expect(nav("Web Search")).toHaveAttribute("aria-current", "page");
      expect(await page.evaluate(() => window.settingsFixture.updates)).toEqual(
        [],
      );
    },
  );
  await verify(
    "legacy fixture without connection field never derives success from URL",
    async () => {
      fixture.reset();
      delete fixture.model.ai.connection;
      await goto("model");
      await expect(check()).toHaveText("Not checked");
      await expect(
        page.getByRole("button", { name: "Test connection" }),
      ).toBeEnabled();
    },
  );
  await verify(
    "missing configuration disables tests without a network probe",
    async () => {
      fixture.reset();
      fixture.model.ai.configured = false;
      fixture.model.ai.base_url = "";
      fixture.model.ai.model = "";
      fixture.model.ai.connection.status = "not_configured";
      const n = probes().length;
      await goto("model");
      await expect(check()).toHaveText("Not configured");
      await expect(
        page.getByRole("button", { name: "Test connection" }),
      ).toBeDisabled();
      await screen("desktop-model-not-configured");
      fixture.search.api_key_set = false;
      fixture.search.api_key_source = "none";
      fixture.search.configured = false;
      fixture.search.connection.status = "not_configured";
      await goto("search");
      await expect(check()).toHaveText("Not configured");
      await expect(
        page.getByRole("button", { name: "Test search" }),
      ).toBeDisabled();
      await screen("desktop-search-not-configured");
      expect(probes()).toHaveLength(n);
    },
  );
  await verify(
    "delayed save readback cannot discard a newer accepted edit",
    async () => {
      fixture.reset();
      await page.goto(`${url}/?race=1`);
      const field = page.getByLabel("Race model");
      await expect(field).toHaveValue("Fixture teaching model");
      await field.fill("Sent synthetic edit");
      const release = fixture.holdRead("model");
      const start = fixture.logs.length;
      await page.getByRole("button", { name: "Race save" }).click();
      await expect
        .poll(() => fixture.logs.slice(start).some((l) => l.method === "GET"))
        .toBe(true);
      await expect(page.getByTestId("race-busy")).toHaveText("save");
      await field.fill("Newer accepted edit");
      release();
      await expect(page.getByTestId("race-busy")).toHaveText("idle");
      await expect(field).toHaveValue("Newer accepted edit");
      await expect(page.getByTestId("race-dirty")).toHaveText("true");
      await expect(page.getByTestId("race-notice")).toContainText(
        "newer edits are not saved",
      );
      expect(fixture.model.ai.model).toBe("Sent synthetic edit");
    },
  );
  await verify(
    "delayed test readback cannot overwrite a new dirty draft",
    async () => {
      await page.getByRole("button", { name: "Race save" }).click();
      await expect(page.getByTestId("race-dirty")).toHaveText("false");
      const release = fixture.holdRead("model");
      const start = fixture.logs.length;
      await page.getByRole("button", { name: "Race test" }).click();
      await expect
        .poll(() => fixture.logs.slice(start).some((l) => l.method === "GET"))
        .toBe(true);
      await expect(page.getByTestId("race-busy")).toHaveText("test");
      await page.getByLabel("Race model").fill("Edited during test readback");
      release();
      await expect(page.getByTestId("race-busy")).toHaveText("idle");
      await expect(page.getByLabel("Race model")).toHaveValue(
        "Edited during test readback",
      );
      await expect(page.getByTestId("race-dirty")).toHaveText("true");
      await expect(page.getByTestId("race-unavailable")).toHaveText("true");
    },
  );
  await verify(
    "390px phone has no horizontal overflow; mobile help click and sections",
    async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await goto("model");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await screen("mobile-model");
      await page
        .getByRole("button", { name: "Help with model API key" })
        .click();
      await expect(page.getByRole("tooltip")).toBeVisible();
      expect(
        await page
          .getByRole("tooltip")
          .evaluate((el) => el.getBoundingClientRect().right <= innerWidth),
      ).toBe(true);
      await page.keyboard.press("Escape");
      await nav("Web Search").click();
      await expect(page.getByLabel("Allow web search")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await screen("mobile-search");
      await nav("Account").click();
      await expect(page.getByLabel("Full name")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await screen("mobile-account");
    },
  );
  await verify(
    "200% layout equivalent keeps labels/actions visible",
    async () => {
      await page.setViewportSize({ width: 640, height: 500 });
      await goto("model");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await expect(page.getByLabel("Model name")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Test connection" }),
      ).toBeVisible();
      await screen("model-200-percent-layout");
    },
  );
  for (const response of result.responses) {
    expect([503, 422]).toContain(response.status);
    expect([
      "/api/teacher/settings",
      "/api/teacher/settings/test",
      "/api/teacher/search-settings",
      "/api/teacher/search-settings/test",
    ]).toContain(response.path);
  }
  expect(result.errors).toEqual([]);
  expect(result.external).toEqual([]);
  result.success = true;
} catch (e) {
  result.success = false;
  result.failure = String(e);
  console.error(e);
  if (page)
    await page
      .screenshot({
        path: path.join(screenshots, "failure.png"),
        fullPage: true,
      })
      .catch(() => {});
  process.exitCode = 1;
} finally {
  if (browser) {
    await browser.close();
    result.cleanup.browser_closed = !browser.isConnected();
  }
  if (server) {
    fixture.releaseAll();
    await new Promise((resolve) => server.close(resolve));
    result.cleanup.server_closed = !server.listening;
  }
  result.check_count = result.checks.length;
  result.screenshot_count = result.screenshots.length;
  result.safe_requests = fixture?.logs ?? [];
  result.scratch = scratch;
  await fs.writeFile(
    path.join(artifacts, "browser-results.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify({
      success: result.success,
      checks: result.check_count,
      screenshots: result.screenshot_count,
      cleanup: result.cleanup,
      failure: result.failure,
    }),
  );
}
