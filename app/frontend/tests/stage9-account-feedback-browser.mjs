// Actual Chrome with explicit synthetic HTTP fixture. NOT backend/security/normalization evidence.
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import net from "node:net";
import { stage9Fixture } from "./stage9-account-feedback-fixture-http.mjs";
const require = createRequire(new URL("../package.json", import.meta.url));
const { chromium, expect } = require("@playwright/test");
const { createServer } = await import(
  pathToFileURL(require.resolve("vite")).href
);
const react = (
  await import(pathToFileURL(require.resolve("@vitejs/plugin-react")).href)
).default;
const root = path.resolve(import.meta.dirname, ".."),
  out = path.join(
    root,
    "artifacts/stage9-account-feedback",
    new Date().toISOString().replace(/[:.]/g, "-"),
  );
await fs.mkdir(out, { recursive: true });
const fixture = stage9Fixture(),
  { controls, counts, rows, users } = fixture;
const checks = [],
  errors = [],
  shots = [],
  external = [];
let server, browser, page, port;
const check = (label) => checks.push(label);
const shot = async (name, fullPage = false) => {
  const file = path.join(out, name + ".png");
  await page.screenshot({
    path: file,
    fullPage,
    animations: "disabled",
    caret: "hide",
  });
  shots.push(file);
};
const listening = (p) =>
  new Promise((resolve) => {
    const socket = net.connect(p, "127.0.0.1");
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => resolve(false));
  });
try {
  server = await createServer({
    configFile: false,
    root,
    plugins: [fixture.plugin, react()],
    server: {
      host: "127.0.0.1",
      port: 0,
      strictPort: false,
      watch: null,
      hmr: false,
    },
    cacheDir: path.join(out, "vite-cache"),
    logLevel: "error",
  });
  await server.listen();
  port = server.httpServer.address().port;
  browser = await chromium.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(12000);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (r) => {
    if (
      !r.url().startsWith(`http://127.0.0.1:${port}`) &&
      !r.url().startsWith("data:")
    )
      external.push(r.url());
  });
  await page.goto(
    `http://127.0.0.1:${port}/tests/stage9-account-feedback-harness.html`,
  );
  await expect(
    page.getByRole("heading", { name: "Account", exact: true }),
  ).toBeVisible();
  const imageData = await page.evaluate(() => {
    function png(width, height, panorama = false) {
      const c = document.createElement("canvas");
      c.width = width;
      c.height = height;
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#00aa00";
      ctx.fillRect(0, 0, width, height);
      if (panorama) {
        ctx.fillStyle = "#ff0000";
        ctx.fillRect(0, 0, 256, height);
        ctx.fillStyle = "#0000ff";
        ctx.fillRect(512, 0, 256, height);
      }
      return c.toDataURL("image/png").split(",")[1];
    }
    return {
      panorama: png(768, 256, true),
      normalized: png(256, 256),
      large: png(5000, 4000),
    };
  });
  fixture.setImage(Buffer.from(imageData.normalized, "base64"));
  const photo = {
    name: "synthetic-panorama.png",
    mimeType: "image/png",
    buffer: Buffer.from(imageData.panorama, "base64"),
  };
  const choose = () => page.getByLabel("Choose avatar image", { exact: true }),
    name = () =>
      page.locator(".profile-page").getByLabel("Full name", { exact: true });
  const avatar = () => page.locator(".page-heading .account-avatar");
  const persisted = () => avatar().locator("img");
  const choosePhoto = async () => {
    await choose().setInputFiles(photo);
    await expect(
      page.getByAltText("Unsaved centered avatar preview"),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Save avatar", exact: true }),
    ).toBeEnabled();
  };
  await expect(avatar().getByRole("img")).toHaveAttribute(
    "aria-label",
    "Avatar initials for Synthetic Student A",
  );
  expect(await page.evaluate(() => window.stage9Dirty())).toBe(false);
  check("Account starts with accessible initials and no dirty state");
  await choose().setInputFiles({
    name: "unsafe.svg",
    mimeType: "image/svg+xml",
    buffer: Buffer.from("<svg/>"),
  });
  await expect(page.getByRole("alert")).toContainText("static PNG");
  expect(counts.upload).toBe(0);
  await choose().setInputFiles({
    name: "fake.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from("not a real image"),
  });
  await expect(page.getByRole("alert")).toContainText("could not be decoded");
  await choose().setInputFiles({
    name: "too-big.png",
    mimeType: "image/png",
    buffer: Buffer.alloc(5 * 1024 * 1024 + 1),
  });
  await expect(page.getByRole("alert")).toContainText("5 MiB");
  await choose().setInputFiles({
    name: "too-many-pixels.png",
    mimeType: "image/png",
    buffer: Buffer.from(imageData.large, "base64"),
  });
  await expect(page.getByRole("alert")).toContainText("16 million");
  expect(counts.upload).toBe(0);
  check(
    "Real Chrome rejects prohibited MIME, fake image, >5MiB and >16M decoded pixels before upload",
  );
  await choosePhoto();
  expect(await page.evaluate(() => window.stage9Dirty())).toBe(true);
  expect(await persisted().count()).toBe(0);
  const crop = await page
    .getByAltText("Unsaved centered avatar preview")
    .evaluate((img) => {
      const c = document.createElement("canvas");
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0);
      return {
        w: c.width,
        h: c.height,
        left: Array.from(ctx.getImageData(0, 128, 1, 1).data),
        right: Array.from(ctx.getImageData(255, 128, 1, 1).data),
      };
    });
  expect(crop).toEqual({
    w: 256,
    h: 256,
    left: [0, 170, 0, 255],
    right: [0, 170, 0, 255],
  });
  check(
    "Actual256 preview pixels are center-cropped, not stretched/CSS-only; candidate is not current avatar",
  );
  await name().fill("Unsaved Display Name");
  await page
    .getByLabel("Current password", { exact: true })
    .fill("SyntheticOld1");
  await page.getByLabel("New password", { exact: true }).fill("SyntheticNext2");
  await page
    .getByLabel("Repeat new password", { exact: true })
    .fill("SyntheticNext2");
  controls.meAfterAvatar = 1;
  await page.getByRole("button", { name: "Save avatar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "accepted, but verification is incomplete",
  );
  await expect(
    page.getByRole("button", { name: "Check saved avatar", exact: true }),
  ).toBeEnabled();
  await expect(choose()).toBeDisabled();
  await expect(name()).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Save avatar", exact: true }),
  ).toBeDisabled();
  await expect(name()).toHaveValue("Unsaved Display Name");
  await expect(
    page.getByLabel("Current password", { exact: true }),
  ).toHaveValue("SyntheticOld1");
  expect(await persisted().count()).toBe(0);
  check(
    "Accepted upload + failed independent /me keeps candidate/name/password and does not claim saved",
  );
  controls.failImage = true;
  const uploads = counts.upload;
  await page
    .getByRole("button", { name: "Check saved avatar", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "image could not be loaded",
  );
  expect(counts.upload).toBe(uploads);
  expect(await persisted().count()).toBe(0);
  check(
    "Image-load failure is separate from projection success; readback retries do not upload again",
  );
  controls.failImage = false;
  await page
    .getByRole("button", { name: "Check saved avatar", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Avatar saved and verified.",
  );
  await expect(persisted()).toHaveAttribute(
    "src",
    users["student-a"].avatar_url,
  );
  await expect(page.locator("header .account-avatar img")).toHaveAttribute(
    "src",
    users["student-a"].avatar_url,
  );
  await expect(page.getByLabel("New password", { exact: true })).toHaveValue(
    "SyntheticNext2",
  );
  await expect(name()).toHaveValue("Unsaved Display Name");
  expect(await page.evaluate(() => window.stage9Dirty())).toBe(true);
  await shot("desktop-account-upload");
  check(
    "Verified persisted avatar appears in Account + reusable header; unrelated dirty fields survive onUpdate",
  );
  await page
    .locator(".profile-page section")
    .filter({
      has: page.getByRole("heading", { name: "Display name", exact: true }),
    })
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(name()).toHaveValue("Unsaved Display Name");
  await expect(page.locator(".profile-page > .notice")).toContainText("Saved");
  expect(counts.profile).toBe(1);
  await page
    .locator(".profile-page section")
    .filter({
      has: page.getByRole("heading", { name: "Change password", exact: true }),
    })
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    page.getByLabel("Current password", { exact: true }),
  ).toHaveValue("");
  await expect(page.getByLabel("New password", { exact: true })).toHaveValue(
    "",
  );
  expect(counts.password).toBe(1);
  expect(await page.evaluate(() => window.stage9Dirty())).toBe(false);
  check(
    "Original display-name save and password save + independent /me still work and clear only their own edits",
  );
  await page.reload();
  await expect(persisted()).toHaveAttribute(
    "src",
    users["student-a"].avatar_url,
  );
  const oldUrl = users["student-a"].avatar_url;
  await choosePhoto();
  await expect(persisted()).toHaveAttribute("src", oldUrl);
  controls.failWrite = true;
  await page.getByRole("button", { name: "Save avatar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("write rejected");
  await expect(
    page.getByAltText("Unsaved centered avatar preview"),
  ).toBeVisible();
  await expect(persisted()).toHaveAttribute("src", oldUrl);
  check(
    "Refresh loads persisted image; replace rejection retains old image and candidate",
  );
  await page
    .getByRole("button", { name: "Reload current avatar", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "unsaved preview has not been applied",
  );
  await expect(
    page.getByAltText("Unsaved centered avatar preview"),
  ).toBeVisible();
  controls.staleAfterAvatar = true;
  await page.getByRole("button", { name: "Save avatar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("could not be verified");
  await expect(persisted()).toHaveAttribute("src", oldUrl);
  const replacements = counts.upload;
  await page
    .getByRole("button", { name: "Check saved avatar", exact: true })
    .click();
  await expect(persisted()).toHaveAttribute(
    "src",
    users["student-a"].avatar_url,
  );
  expect(counts.upload).toBe(replacements);
  expect(users["student-a"].avatar_url).not.toBe(oldUrl);
  expect(
    (await page.request.get(`http://127.0.0.1:${port}${oldUrl}`)).status(),
  ).toBe(404);
  check(
    "Wrong /me revision blocks visual success; replacement readback updates exact URL and fixture invalidates old URL",
  );
  controls.failWrite = true;
  const activeUrl = users["student-a"].avatar_url;
  await page
    .getByRole("button", { name: "Remove avatar", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("write rejected");
  await expect(persisted()).toHaveAttribute("src", activeUrl);
  controls.meAfterAvatar = 1;
  await page
    .getByRole("button", { name: "Remove avatar", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Check saved avatar", exact: true }),
  ).toBeEnabled();
  const removals = counts.remove;
  await page
    .getByRole("button", { name: "Check saved avatar", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Avatar removed and verified.",
  );
  expect(counts.remove).toBe(removals);
  expect(await persisted().count()).toBe(0);
  await expect(avatar().getByRole("img")).toHaveAttribute(
    "aria-label",
    "Avatar initials for Unsaved Display Name",
  );
  check(
    "Remove failure keeps image; accepted delete readback retries GET only and restores initials",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await choosePhoto();
  await choose().scrollIntoViewIfNeeded();
  await expect(choose()).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await shot("mobile-account-preview");
  await page
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  expect(await page.evaluate(() => window.stage9Dirty())).toBe(false);
  check(
    "390px Account preview/file control/actions fit; discard resets only avatar dirty state",
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("button", { name: "Feedback fixture", exact: true })
    .click();
  await expect(page.getByText("1–25 of 31", { exact: true })).toBeVisible();
  await expect(page.locator("[data-feedback-id]")).toHaveCount(25);
  await expect(
    page.getByRole("button", { name: "Administrator inbox", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.getByText("26–31 of 31", { exact: true })).toBeVisible();
  await expect(page.locator("[data-feedback-id]")).toHaveCount(6);
  await expect(
    page.getByRole("button", { name: "Next page", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Previous page", exact: true })
    .click();
  await expect(page.getByText("1–25 of 31", { exact: true })).toBeVisible();
  check(
    "Own history uses real total and both pagination pages with no hidden truncation; student has no Inbox",
  );
  controls.failList = 1;
  await page.getByRole("button", { name: "Refresh list", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("list unavailable");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator("[data-feedback-id]")).toHaveCount(25);
  check(
    "List GET failure has independent retry rather than simulated empty history",
  );
  const subject = () => page.getByLabel("Subject", { exact: true }),
    message = () => page.getByLabel("Message", { exact: true });
  await subject().fill("Student A unsent draft");
  await message().fill("Account A only");
  page.once("dialog", (d) => d.dismiss());
  await page
    .getByRole("button", { name: "Account fixture", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Feedback", exact: true }),
  ).toBeVisible();
  check(
    "Feedback draft activates shared navigation guard and cancellation retains text",
  );
  await page
    .getByLabel("Fixture account", { exact: true })
    .selectOption("student-b");
  await expect(subject()).toHaveValue("");
  await expect(page.getByText("1–2 of 2", { exact: true })).toBeVisible();
  await subject().fill("Student B unsent draft");
  await message().fill("Account B only");
  await page
    .getByLabel("Fixture account", { exact: true })
    .selectOption("student-a");
  await expect(subject()).toHaveValue("Student A unsent draft");
  await expect(message()).toHaveValue("Account A only");
  await expect(page.getByText("1–25 of 31", { exact: true })).toBeVisible();
  check(
    "Switching account remounts state; each account has separate durable draft and own history",
  );
  await subject().fill("s".repeat(161));
  await expect(subject()).toHaveValue("s".repeat(161));
  await expect(page.getByRole("alert")).toContainText("kept in full");
  await expect(
    page.getByRole("button", { name: "Send feedback", exact: true }),
  ).toBeDisabled();
  await subject().fill("🧑".repeat(160));
  await expect(
    page.getByRole("button", { name: "Send feedback", exact: true }),
  ).toBeEnabled();
  await message().fill("m".repeat(6001));
  await expect(message()).toHaveValue("m".repeat(6001));
  await expect(message()).toHaveAttribute("aria-invalid", "true");
  await expect(
    page.getByRole("button", { name: "Send feedback", exact: true }),
  ).toBeDisabled();
  await subject().fill("Student A unsent draft");
  await message().fill("Account A only");
  check(
    "Real controls retain over-limit text with explicit warning, disable sends and count Unicode codepoints without silent truncation",
  );
  controls.failCreate = 422;
  await page
    .getByRole("button", { name: "Send feedback", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("submission rejected");
  await expect(subject()).toBeEnabled();
  await expect(subject()).toHaveValue("Student A unsent draft");
  check(
    "Definitively rejected POST retains editable fields and releases failed attempt",
  );
  await page.getByLabel("Category", { exact: true }).selectOption("bug");
  await subject().fill("Unknown result, exact retry");
  await message().fill("Raw line one\n\nRaw line two");
  controls.unknownCreate = true;
  controls.failRequest = 1;
  await page
    .getByRole("button", { name: "Send feedback", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Submission could not be confirmed",
  );
  await expect(subject()).toBeDisabled();
  const creates = counts.create,
    createdRow = rows.at(-1),
    unknownId = createdRow.request_id;
  const savedAttempt = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("aicademiya:feedback:v1:student-a")),
  );
  expect(fixture.createRequests.at(-1).request_id).not.toBe(
    fixture.createRequests.at(-2).request_id,
  );
  expect(savedAttempt.attempt.request_id).toBe(unknownId);
  await page.reload();
  await expect(
    page.getByRole("button", {
      name: "Check saved submission / retry",
      exact: true,
    }),
  ).toBeEnabled();
  await expect(subject()).toHaveValue("Unknown result, exact retry");
  await page
    .getByRole("button", {
      name: "Check saved submission / retry",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Feedback sent and verified." }),
  ).toBeVisible();
  expect(counts.create).toBe(creates);
  expect(rows.filter((r) => r.request_id === unknownId)).toHaveLength(1);
  await expect(subject()).toHaveValue("");
  expect(
    await page.evaluate(() =>
      localStorage.getItem("aicademiya:feedback:v1:student-a"),
    ),
  ).toBeNull();
  check(
    "Unknown committed POST survives refresh; request GET recovers exact identity without duplicate POST and clears only acknowledged draft",
  );
  const literalSubject = "<script>not executable</script> literal subject";
  const literalMessage = "<img src=x onerror=alert(1)>\n\n" + "z".repeat(5968);
  expect(literalMessage.length).toBeLessThanOrEqual(6000);
  await subject().fill(literalSubject);
  await message().fill(literalMessage);
  controls.detailAfterCreate = 1;
  await page
    .getByRole("button", { name: "Send feedback", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "accepted, but verification is incomplete",
  );
  await expect(subject()).toHaveValue(literalSubject);
  await expect(message()).toHaveValue(literalMessage);
  const acceptedCreates = counts.create;
  await page
    .getByRole("button", {
      name: "Check saved submission / retry",
      exact: true,
    })
    .click();
  await expect(page.locator(".feedback-subject")).toHaveText(literalSubject);
  await expect(page.locator(".feedback-literal").first()).toHaveText(
    literalMessage,
  );
  expect(
    await page.locator(".feedback-detail script, .feedback-detail img").count(),
  ).toBe(0);
  expect(counts.create).toBe(acceptedCreates);
  await expect(page.getByText("1–25 of 33", { exact: true })).toBeVisible();
  await shot("desktop-feedback-own-detail");
  await page
    .getByRole("heading", { name: "Feedback", exact: true })
    .evaluate((e) => e.scrollIntoView({ block: "start" }));
  await shot("desktop-feedback-own");
  check(
    "Accepted POST + failed exact GET keeps full literal text; GET-only retry acknowledges escaped detail without hidden truncation",
  );
  await page.getByLabel("Filter category", { exact: true }).selectOption("bug");
  await expect(page.locator("[data-feedback-id]")).toHaveCount(
    rows.filter((r) => r.author_id === "student-a" && r.category === "bug")
      .length,
  );
  await page
    .getByLabel("Filter status", { exact: true })
    .selectOption("reviewed");
  await expect(
    page.getByText("0 feedback items", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Filter category", { exact: true }).selectOption("");
  await page.getByLabel("Filter status", { exact: true }).selectOption("");
  await expect(page.getByText("1–25 of 33", { exact: true })).toBeVisible();
  check(
    "Own category/status filters report exact filtered totals and empty state",
  );
  await page
    .getByLabel("Fixture account", { exact: true })
    .selectOption("admin");
  await expect(page.getByText("1–1 of 1", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Administrator inbox", exact: true })
    .click();
  await expect(
    page.getByText(`1–25 of ${rows.length}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Send feedback", exact: true }),
  ).toHaveCount(0);
  check(
    "Admin defaults to own list; explicit Inbox switches scope and hides own submission form",
  );
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(
    page.getByText(`26–${rows.length} of ${rows.length}`, { exact: true }),
  ).toBeVisible();
  await expect(page.locator("[data-feedback-id]")).toHaveCount(
    rows.length - 25,
  );
  await page
    .getByRole("button", { name: "Previous page", exact: true })
    .click();
  await expect(
    page.getByText(`1–25 of ${rows.length}`, { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Filter category", { exact: true }).selectOption("bug");
  await expect(page.locator("[data-feedback-id]")).toHaveCount(
    rows.filter((r) => r.category === "bug").length,
  );
  await page
    .getByLabel("Filter status", { exact: true })
    .selectOption("reviewed");
  await expect(
    page.getByText("0 feedback items", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Filter category", { exact: true }).selectOption("");
  await page.getByLabel("Filter status", { exact: true }).selectOption("");
  await expect(
    page.getByText(`1–25 of ${rows.length}`, { exact: true }),
  ).toBeVisible();
  check(
    "Admin Inbox pagination and combined filters use exact all-account totals",
  );
  await page.locator('[data-feedback-id="a-30"]').click();
  await expect(page.getByLabel("Your reply", { exact: true })).toHaveValue("");
  await page
    .getByLabel("Review status", { exact: true })
    .selectOption("reviewed");
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(page.locator(".feedback-detail .feedback-status")).toHaveText(
    "Reviewed",
  );
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "No reply yet.",
  );
  expect(rows.find((row) => row.id === "a-30").reply).toBe("");
  await shot("desktop-feedback-inbox-reviewed");
  await page.getByLabel("Review status", { exact: true }).selectOption("new");
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(page.locator(".feedback-detail .feedback-status")).toHaveText(
    "New",
  );
  check(
    "Admin can mark Reviewed without inventing a reply, and explicitly return status to New",
  );
  const latestId = rows.at(-1).id,
    otherId = rows.at(-2).id;
  controls.failDetail = 1;
  await page.locator(`[data-feedback-id="${latestId}"]`).click();
  await expect(
    page.locator(".feedback-detail").getByRole("alert"),
  ).toContainText("readback unavailable");
  await page
    .locator(".feedback-detail")
    .getByRole("button", { name: "Try again", exact: true })
    .click();
  await expect(page.locator(".feedback-subject")).toHaveText(literalSubject);
  await expect(
    page.getByRole("heading", { name: "Feedback detail", exact: true }),
  ).toBeInViewport();
  check(
    "Detail GET failure exposes retry; opening detail moves keyboard focus to a reachable heading",
  );
  const held = fixture.hold(latestId);
  await page.locator(`[data-feedback-id="${latestId}"]`).click();
  await held.entered;
  await expect(
    page.getByText("Loading selected feedback…", { exact: true }),
  ).toBeVisible();
  await page.locator(`[data-feedback-id="${otherId}"]`).click();
  await expect(page.locator(".feedback-subject")).toHaveText(
    rows.find((r) => r.id === otherId).subject,
  );
  const lateResponse = page.waitForResponse((r) =>
    r.url().endsWith(`/api/admin/feedback/${latestId}`),
  );
  held.release();
  await (await lateResponse).finished();
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await expect(page.locator(".feedback-subject")).toHaveText(
    rows.find((r) => r.id === otherId).subject,
  );
  check(
    "Explicit HTTP hold/release proves late detail A cannot replace current detail B",
  );
  await page.locator(`[data-feedback-id="${latestId}"]`).click();
  await expect(page.locator(".feedback-subject")).toHaveText(literalSubject);
  await expect(page.locator(".feedback-author")).toContainText(
    "student-a@example.invalid",
  );
  const reply = () => page.getByLabel("Your reply", { exact: true });
  await reply().fill("Draft reply for literal A\nKept separately");
  page.once("dialog", (d) => d.dismiss());
  await page.locator(`[data-feedback-id="${otherId}"]`).click();
  await expect(reply()).toHaveValue(
    "Draft reply for literal A\nKept separately",
  );
  page.once("dialog", (d) => d.accept());
  await page.locator(`[data-feedback-id="${otherId}"]`).click();
  await expect(reply()).toHaveValue("");
  await reply().fill("Draft reply for B");
  page.once("dialog", (d) => d.accept());
  await page.locator(`[data-feedback-id="${latestId}"]`).click();
  await expect(reply()).toHaveValue(
    "Draft reply for literal A\nKept separately",
  );
  expect(await page.evaluate(() => window.stage9Dirty())).toBe(true);
  check(
    "Admin detail switch cancellation keeps current draft; accepted switch isolates and restores per-item dirty replies",
  );
  controls.failUpdate = true;
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("reply rejected");
  await expect(reply()).toHaveValue(
    "Draft reply for literal A\nKept separately",
  );
  await expect(reply()).toBeEnabled();
  check(
    "Rejected admin PATCH retains editable dirty reply/status without changing saved state",
  );
  const target = rows.find((r) => r.id === latestId);
  target.reply = "Concurrent saved reply";
  target.revision++;
  await page
    .getByLabel("Review status", { exact: true })
    .selectOption("reviewed");
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Another administrator" }),
  ).toBeVisible();
  await expect(reply()).toHaveValue(
    "Draft reply for literal A\nKept separately",
  );
  await expect(
    page.getByRole("button", { name: "Save reply and status", exact: true }),
  ).toBeDisabled();
  check(
    "PATCH expected_revision409 preserves human draft and blocks blind retry",
  );
  await page
    .getByRole("button", {
      name: "Load latest revision, keep draft",
      exact: true,
    })
    .click();
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "Concurrent saved reply",
  );
  await expect(reply()).toHaveValue(
    "Draft reply for literal A\nKept separately",
  );
  await expect(
    page.getByText("Editing revision 2.", { exact: false }),
  ).toBeVisible();
  controls.detailAfterUpdate = 1;
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "accepted, but verification is incomplete",
  );
  await expect(reply()).toHaveValue(
    "Draft reply for literal A\nKept separately",
  );
  const updates = counts.update;
  await page
    .getByRole("button", { name: "Check saved reply", exact: true })
    .click();
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "Draft reply for literal A\nKept separately",
  );
  expect(counts.update).toBe(updates);
  expect(target.status).toBe("reviewed");
  expect(target.revision).toBe(3);
  check(
    "Explicit latest-revision review keeps draft; accepted PATCH readback failure retries GET only and verifies New/Reviewed+reply",
  );
  await reply().fill("Unknown PATCH result acknowledged by exact GET");
  controls.unknownUpdate = true;
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("result is unknown");
  const unknownUpdates = counts.update;
  await page
    .getByRole("button", { name: "Check saved reply", exact: true })
    .click();
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "Unknown PATCH result acknowledged by exact GET",
  );
  expect(counts.update).toBe(unknownUpdates);
  check(
    "Lost committed PATCH response checks independent exact revision without repeating mutation",
  );
  await reply().fill("q".repeat(6001));
  await expect(reply()).toHaveValue("q".repeat(6001));
  await expect(page.getByRole("alert")).toContainText("kept in full");
  await expect(
    page.getByRole("button", { name: "Save reply and status", exact: true }),
  ).toBeDisabled();
  await reply().fill("Pending reply verification");
  const replyHold = fixture.hold(latestId);
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await replyHold.entered;
  await expect(reply()).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "My feedback", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(`[data-feedback-id="${otherId}"]`)).toBeDisabled();
  page.once("dialog", (d) => d.dismiss());
  await page
    .getByRole("button", { name: "Account fixture", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Feedback", exact: true }),
  ).toBeVisible();
  const pendingRead = page.waitForResponse((r) =>
    r.url().endsWith(`/api/admin/feedback/${latestId}`),
  );
  replyHold.release();
  await (await pendingRead).finished();
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "Pending reply verification",
  );
  check(
    "Reply over-limit is retained; explicit pending GET holds disable mutation/selection and activate navigation guard",
  );
  await page
    .getByRole("heading", { name: "Reply and review", exact: true })
    .evaluate((e) => e.scrollIntoView({ block: "start" }));
  await shot("desktop-feedback-inbox-reply");
  await page.setViewportSize({ width: 390, height: 844 });
  await reply().fill("Mobile administrator reply");
  await reply().scrollIntoViewIfNeeded();
  await expect(reply()).toBeInViewport();
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("button", { name: "Save reply and status", exact: true }),
  ).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await shot("mobile-feedback-inbox-reply");
  await page
    .getByRole("button", { name: "Save reply and status", exact: true })
    .click();
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "Mobile administrator reply",
  );
  check(
    "390px Inbox/reply and 6000-character detail have no horizontal overflow; action is viewport-reachable",
  );
  await page
    .getByLabel("Fixture account", { exact: true })
    .selectOption("student-a");
  await expect(page.getByText("1–25 of 33", { exact: true })).toBeVisible();
  await page.locator(`[data-feedback-id="${latestId}"]`).click();
  await expect(page.locator(".feedback-literal").nth(1)).toHaveText(
    "Mobile administrator reply",
  );
  await expect(page.locator(".feedback-detail .feedback-status")).toHaveText(
    "Reviewed",
  );
  await expect(page.getByLabel("Your reply", { exact: true })).toHaveCount(0);
  await shot("mobile-feedback-own-detail");
  await page.getByLabel("Filter status", { exact: true }).focus();
  await page.keyboard.press("r");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Filter status", { exact: true })).toHaveValue(
    "reviewed",
  );
  await expect(page.getByLabel("Filter status", { exact: true })).toBeEnabled();
  await page.getByLabel("Filter status", { exact: true }).focus();
  await expect(page.getByLabel("Filter status", { exact: true })).toBeFocused();
  check(
    "Author independently reads admin human reply/status; mobile own detail is read-only and filter is keyboard accessible",
  );
  await page
    .getByLabel("Fixture account", { exact: true })
    .selectOption("student-b");
  await expect(subject()).toHaveValue("Student B unsent draft");
  await expect(message()).toHaveValue("Account B only");
  await expect(page.locator(".feedback-subject")).toHaveCount(0);
  await expect(page.getByText("1–2 of 2", { exact: true })).toBeVisible();
  check(
    "Final account switch exposes no prior selected detail/reply and restores only that account draft",
  );
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
  check(
    "No Chrome page exceptions or external network calls; all fixture data is synthetic",
  );
} catch (e) {
  errors.push(String(e));
  if (page) await shot("failure").catch(() => {});
  process.exitCode = 1;
} finally {
  await browser?.close();
  await server?.close();
  const closed = port ? !(await listening(port)) : true;
  const result = {
    status: errors.length || !closed ? "failed" : "passed",
    checks,
    errors,
    screenshots: shots,
    counts,
    external_requests: external,
    owned_browser_closed: true,
    owned_server_closed: closed,
    evidence:
      "Actual React + installed Chrome + explicit synthetic Vite HTTP fixture. NOT real FastAPI/SQLite/auth/image-normalization/data-retention proof.",
  };
  await fs.writeFile(
    path.join(out, "result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify({
      status: result.status,
      checks: checks.length,
      errors,
      result: path.join(out, "result.json"),
    }),
  );
}
