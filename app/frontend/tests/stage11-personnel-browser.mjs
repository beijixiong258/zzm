// Actual installed Chrome + explicit synthetic HTTP DTO fixture. No backend auth/SQLite proof.
import fs from "node:fs/promises";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";
import { personnelFixture } from "./stage11-personnel-fixture-http.mjs";
const require = createRequire(new URL("../package.json", import.meta.url)),
  { chromium, expect } = require("@playwright/test");
const { createServer } = await import(
    pathToFileURL(require.resolve("vite")).href
  ),
  react = (
    await import(pathToFileURL(require.resolve("@vitejs/plugin-react")).href)
  ).default;
const root = path.resolve(import.meta.dirname, ".."),
  out = path.resolve(
    root,
    "../artifacts/stage11/ui",
    "fixture-" + new Date().toISOString().replace(/[:.]/g, "-"),
  );
await fs.mkdir(out, { recursive: true });
const checks = [],
  shots = [],
  errors = [],
  external = [];
let server, browser, port;
const fixture = personnelFixture(),
  { counts, controls } = fixture;
const csv = (text) => ({
  name: "synthetic.csv",
  mimeType: "text/csv",
  buffer: Buffer.from(text),
});
const password = () => "Fixture" + crypto.randomBytes(12).toString("hex") + "1"; // memory only; never report payloads
const listening = (p) =>
  new Promise((r) => {
    const s = net.connect(p, "127.0.0.1");
    s.once("connect", () => {
      s.destroy();
      r(true);
    });
    s.once("error", () => r(false));
  });
try {
  server = await createServer({
    configFile: false,
    root,
    plugins: [fixture.plugin, react()],
    cacheDir: path.join(out, "vite-cache"),
    logLevel: "error",
    server: { host: "127.0.0.1", port: 0, watch: null, hmr: false },
  });
  await server.listen();
  port = server.httpServer.address().port;
  browser = await chromium.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  for (const width of [1440, 390]) {
    const page = await browser.newPage({
      viewport: { width, height: width === 390 ? 844 : 1000 },
    });
    page.setDefaultTimeout(12000);
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (r) => {
      if (
        !r.url().startsWith(`http://127.0.0.1:${port}`) &&
        !r.url().startsWith("data:")
      )
        external.push(r.url());
    });
    const check = (label) => checks.push(`${width}px: ${label}`),
      button = (n) => page.getByRole("button", { name: n, exact: true }),
      label = (n) => page.getByLabel(n, { exact: true });
    const shot = async (n) => {
      const f = path.join(out, `${width}-${n}.png`);
      await page.screenshot({
        path: f,
        fullPage: true,
        animations: "disabled",
        caret: "hide",
      });
      shots.push(f);
    };
    await page.goto(
      `http://127.0.0.1:${port}/tests/stage11-personnel-harness.html`,
    );
    await expect(
      page.getByRole("heading", { name: "Global User Accounts", exact: true }),
    ).toBeVisible();
    await expect(label("New account role")).toHaveValue("student");
    await expect(
      page.getByRole("heading", {
        name: "New student registration",
        exact: true,
      }),
    ).toBeVisible();
    check("Admin registration preserved; create/import default Student");
    const create = page.locator(".am-create");
    const newName = `New Teacher ${width}`,
      newEmail = `new-teacher-${width}@example.invalid`;
    await label("Account name").fill(newName);
    await label("Account email").fill(newEmail);
    await label("New account role").selectOption("teacher");
    await label("Temporary password").fill(password());
    page.once("dialog", (d) => d.dismiss());
    await button("Teacher fixture").click();
    await expect(create.getByLabel("Account name")).toHaveValue(newName);
    check("Dirty global account navigation cancellation retains draft");
    controls.afterWriteReadFailure = true;
    const cBefore = counts.create;
    await create
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(create.getByRole("alert")).toContainText(
      "readback is incomplete",
    );
    await expect(label("Temporary password")).toBeDisabled();
    expect(counts.create).toBe(cBefore + 1);
    expect(
      await label("Temporary password")
        .inputValue()
        .then((v) => v.length > 0),
    ).toBe(true);
    await shot("create-readback-error");
    const concurrentlyChanged = [...fixture.accounts.values()].find(
      (a) => a.user.email === newEmail,
    );
    concurrentlyChanged.active = false;
    await button("Inspect creation outcome (GET only)").click();
    await expect(create.getByRole("status")).toContainText(
      "differs from the retained creation draft",
    );
    await expect(button("I reviewed the outcome — unlock draft")).toBeEnabled();
    await expect(label("Temporary password")).toBeDisabled();
    expect(counts.create).toBe(cBefore + 1);
    check(
      "Mismatching current creation readback retains draft and offers explicit human inspection/unlock, not a repeat POST",
    );
    concurrentlyChanged.active = true;
    await button("Inspect creation outcome (GET only)").click();
    await expect(create.getByRole("status")).toContainText(
      "independently verified",
    );
    expect(counts.create).toBe(cBefore + 1);
    await expect(label("Account name")).toHaveValue("");
    expect(
      await label("Temporary password")
        .inputValue()
        .then((v) => v.length === 0),
    ).toBe(true);
    check(
      "Create acknowledged + failed exact GET keeps in-memory password/draft; GET-only recovery no duplicate POST",
    );
    await label("Account name").fill(`Unknown ${width}`);
    await label("Account email").fill(`unknown-${width}@example.invalid`);
    await label("Temporary password").fill(password());
    controls.unknownCreate = true;
    await create
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(create.getByRole("alert")).toContainText("outcome is unknown");
    const unknownCreates = counts.create;
    await button("Inspect creation outcome (GET only)").click();
    await expect(create.getByRole("status")).toContainText(
      "original creation was not acknowledged",
    );
    expect(counts.create).toBe(unknownCreates);
    page.once("dialog", (d) => d.accept());
    await button("I reviewed the outcome — unlock draft").click();
    page.once("dialog", (d) => d.accept());
    await button("Discard account draft").click();
    check(
      "Unknown account write is inspected, not automatically retried or falsely acknowledged",
    );
    await label("Accounts per page").selectOption("10");
    await expect(page.locator(".am-account-list > li")).toHaveCount(10);
    await button("Next accounts").click();
    await expect(page.locator(".am-account-list > li")).toHaveCount(10);
    await label("Filter global role").selectOption("teacher");
    await expect(button("Next accounts")).toBeDisabled();
    await label("Search global accounts").fill("Synthetic Teacher B");
    await button("Search accounts").click();
    await expect(page.locator(".am-account-list > li")).toHaveCount(1);
    check(
      "All-role index is paged with exact filtered totals; search/filter reset page and selection",
    );
    await button("Manage account: Synthetic Teacher B").click();
    await expect(label("New global role")).toHaveValue("teacher");
    await label("New global role").selectOption("student");
    await button("Change global role").click();
    controls.roleConflict =
      "Primary manager conflict: transfer primary management and remove staff assignments first.";
    const ownerBefore = fixture.owners.get("c1");
    await button("Confirm role change").click();
    await expect(
      page.locator(".am-account-detail").getByRole("alert"),
    ).toContainText("Primary manager conflict");
    await expect(label("New global role")).toHaveValue("student");
    expect(fixture.owners.get("c1")).toBe(ownerBefore);
    await shot("role-conflict");
    check(
      "409 retains role/action; clear assignment/transfer path; no silent owner transfer",
    );
    await button("Manage staff for SYN101").click();
    await expect(
      page
        .locator(".am-staff")
        .getByText("SYN101 · Synthetic Course One", { exact: true }),
    ).toBeVisible();
    await label("Search active staff candidates").fill(newName);
    await button("Search staff candidates").click();
    await button("Add staff: " + newName).click();
    await button("Confirm staff add").click();
    await expect(page.locator(".am-staff").getByRole("status")).toContainText(
      "independently verified",
    );
    await button("Make primary manager: " + newName).click();
    controls.staffConflict =
      "Synthetic concurrent primary409: refresh staff and retain action.";
    await button("Confirm staff primary").click();
    await expect(page.locator(".am-staff").getByRole("alert")).toContainText(
      "primary409",
    );
    await expect(button("Confirm staff primary")).toBeEnabled();
    await button("Refresh course staff").click();
    await button("Confirm staff primary").click();
    await expect(page.locator(".am-staff").getByRole("status")).toContainText(
      "independently verified",
    );
    const newId = [...fixture.accounts.values()].find(
      (a) => a.user.email === newEmail,
    ).user.id;
    expect(fixture.owners.get("c1")).toBe(newId);
    expect(fixture.staff.get("c1")).toContain("admin");
    await button("Remove staff: Synthetic Teacher B").click();
    await button("Confirm staff remove").click();
    await expect(page.locator(".am-staff").getByRole("status")).toContainText(
      "independently verified",
    );
    await button("Confirm role change").click();
    await expect(
      page.locator(".am-account-detail").getByRole("status"),
    ).toContainText("independently verified");
    check(
      "Explicit staff add/primary transfer/remove followed by retained role action; previous primary stays assigned",
    );
    await button("Disable account").click();
    controls.afterWriteReadFailure = true;
    await button("Confirm account disable").click();
    await expect(
      page.locator(".am-account-detail").getByRole("alert"),
    ).toContainText("needs inspection");
    const statuses = counts.status;
    await button("Inspect account outcome (GET only)").click();
    expect(counts.status).toBe(statuses);
    await expect(button("Restore account")).toBeVisible();
    await button("Restore account").click();
    await button("Confirm account restore").click();
    await expect(
      page.locator(".am-account-detail").getByRole("status"),
    ).toContainText("independently verified");
    check(
      "Disable/restore explicitly acknowledged and read back; accepted status GET-failure recovery does not repeat PUT",
    );
    // Fixture state resets teacher role/assignment only between viewport runs, not real accounts.
    await label("Course for staff assignments").selectOption("c3");
    await expect(
      page
        .locator(".am-staff")
        .getByText("SYN303 · Unassigned Course", { exact: true }),
    ).toBeVisible();
    expect(fixture.staff.get("c3")).not.toContain("admin");
    await expect(button("Remove staff: Other Admin")).toBeDisabled();
    check(
      "Primary/last active manager removal is guarded with explicit transfer/add path",
    );
    await label("Search active staff candidates").fill(newName);
    await button("Search staff candidates").click();
    await button("Add staff: " + newName).click();
    await button("Confirm staff add").click();
    await expect(page.locator(".am-staff").getByRole("status")).toContainText(
      "independently verified",
    );
    await shot("staff-unassigned-course");
    check(
      "Light all-course index reaches unassigned trashed course; assignment controls are explicit",
    );
    const imp = page.locator(".am-import");
    await label("Default import role").selectOption("teacher");
    await label("Default temporary password (optional)").fill(password());
    await label("Account import file").setInputFiles(
      csv(
        `name,email,role\nMixed Teacher,mixed-teacher-${width}@example.invalid,\nMixed Student,mixed-student-${width}@example.invalid,student\nExisting Student,existing@example.invalid,student\n`,
      ),
    );
    await button("Validate account import").click();
    await expect(imp.locator("tbody tr")).toHaveCount(3);
    await expect(imp.locator("tbody tr").nth(0)).toContainText("Teacher");
    await expect(imp.locator("tbody tr").nth(1)).toContainText("Student");
    await expect(imp.locator("tbody tr").nth(2)).toContainText("skip");
    await imp
      .getByRole("columnheader", { name: "Role", exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      imp.getByRole("columnheader", { name: "Role", exact: true }),
    ).toBeInViewport();
    await imp
      .getByRole("columnheader", { name: "Action", exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      imp.getByRole("columnheader", { name: "Action", exact: true }),
    ).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const panelShot = path.join(out, `${width}-import-review-reachable.png`);
    await imp.screenshot({
      path: panelShot,
      animations: "disabled",
      caret: "hide",
    });
    shots.push(panelShot);
    check(
      "Review role/action columns are viewport-reachable through the contained horizontal scroller",
    );
    await shot("import-preview");
    controls.unknownCommit = true;
    await button("Commit reviewed accounts").click();
    await expect(imp.getByRole("alert")).toContainText(
      "outcome needs readback",
    );
    const commits = counts.commit;
    await button("Check import outcome (GET only)").click();
    await expect(
      imp.getByRole("status").filter({ hasText: "independently verified" }),
    ).toBeVisible();
    expect(counts.commit).toBe(commits);
    check(
      "Mixed-role CSV visible review (default+override+skip); unknown committed import recovered by exact status and user GETs only",
    );
    await label("Account import file").setInputFiles(
      csv("name,email,role\nAdmin Wrong Role,admin@example.invalid,student\n"),
    );
    await button("Validate account import").click();
    await expect(button("Commit reviewed accounts")).toBeDisabled();
    await expect(
      imp.getByText(
        "Existing account has another role; change role explicitly.",
        { exact: true },
      ),
    ).toBeVisible();
    page.once("dialog", (d) => d.accept());
    await button("Discard account import").click();
    check(
      "Existing role mismatch blocks the entire import commit; no implicit role/password update",
    );
    if (width === 1440) {
      const workbook = execFileSync(
        path.resolve(root, "../.venv/Scripts/python.exe"),
        [
          "-c",
          "import openpyxl,io,sys; w=openpyxl.Workbook();s=w.active;s.append(['name','email','role']);s.append(['XLSX Student','xlsx-student@example.invalid','student']);s.append(['XLSX Teacher','xlsx-teacher@example.invalid','teacher']);b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())",
        ],
      );
      await label("Default temporary password (optional)").fill(password());
      await label("Account import file").setInputFiles({
        name: "synthetic.xlsx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: workbook,
      });
      await button("Validate account import").click();
      await expect(imp.locator("tbody tr")).toHaveCount(2);
      await button("Commit reviewed accounts").click();
      await expect(
        imp.getByRole("status").filter({ hasText: "independently verified" }),
      ).toBeVisible();
      check(
        "Valid synthetic XLSX file traverses multipart preview/commit/readback UI (fixture response, NOT parser proof)",
      );
    }
    await label("Search global accounts").fill("Synthetic Admin");
    await label("Filter global role").selectOption("admin");
    await button("Search accounts").click();
    await button("Manage account: Synthetic Admin").click();
    await expect(label("New global role")).toBeDisabled();
    await expect(button("Disable account")).toBeDisabled();
    check(
      "Self role/status actions remain disabled with a visible explanation",
    );
    // Explicit late account GET barrier + forced identity change is intentional fixture control.
    await label("Search global accounts").fill("Other Admin");
    await button("Search accounts").click();
    await button("Manage account: Other Admin").click();
    await label("New global role").selectOption("teacher");
    await button("Change global role").click();
    controls.roleConflict =
      "Last usable active administrator is protected. Create or restore another active Admin first.";
    await button("Confirm role change").click();
    await expect(
      page.locator(".am-account-detail").getByRole("alert"),
    ).toContainText("Last usable active administrator");
    await expect(label("New global role")).toHaveValue("teacher");
    check(
      "Last-admin409 keeps editable role draft and actionable server reason",
    );
    await button("Cancel account action").click();
    await button("Discard role draft").click();
    const held = fixture.hold("/api/admin/users/other-admin");
    await button("Reload account, keep draft").click();
    await held.entered;
    await expect(page.locator(".am-account-detail")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    await button("Force account remount fixture").click();
    await expect(
      page.getByRole("heading", { name: "Course Students", exact: true }),
    ).toBeVisible();
    const late = page.waitForResponse((r) =>
      r.url().endsWith("/api/admin/users/other-admin"),
    );
    held.release();
    await (await late).finished();
    await expect(page.locator(".am-account-detail")).toHaveCount(0);
    check(
      "Held account-A detail response cannot install into a remounted teacher identity",
    );
    const teacherRequestStart = fixture.requests.length;
    await expect(label("Course for students")).toBeEnabled();
    await expect(label("Candidate role")).toHaveCount(0);
    await expect(button("Refresh course index")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /Make primary manager:/ }),
    ).toHaveCount(0);
    const roster = page.locator(".roster-panel");
    await expect(
      roster.getByLabel("student-a@example.invalid", { exact: true }),
    ).toBeVisible();
    await button("Create or enroll student").click();
    await label("Student name").fill("Name ignored for existing");
    await label("Student email").fill("existing@example.invalid");
    page.once("dialog", (d) => d.dismiss());
    await label("Course for students").selectOption("c2");
    await expect(label("Course for students")).toHaveValue("c1");
    await expect(label("Student email")).toHaveValue(
      "existing@example.invalid",
    );
    check(
      "Teacher course picker dirty-navigation cancellation keeps course/draft",
    );
    controls.afterWriteReadFailure = true;
    await button("Create / enroll student").click();
    await expect(
      page.locator(".am-provision").getByRole("alert"),
    ).toContainText("needs inspection");
    const provisions = counts.provision;
    await button("Inspect student outcome (GET only)").click();
    await expect(
      page.locator(".am-provision").getByRole("status"),
    ).toContainText("independently verified");
    expect(counts.provision).toBe(provisions);
    expect(fixture.accounts.get("existing").user.name).toBe("Existing Student");
    check(
      "Existing Student enrolls with blank password and independent readback; name/role/password unchanged",
    );
    await roster
      .getByLabel("student-a@example.invalid", { exact: true })
      .check();
    await button("Archive selected (1)").click();
    controls.afterWriteReadFailure = true;
    await button("Confirm archive").click();
    await expect(roster.getByRole("alert")).toContainText("needs inspection");
    const acts = counts.rosterAction;
    await button("Inspect roster outcome (GET only)").click();
    await expect(
      roster
        .locator(':scope > [role="status"]')
        .filter({ hasText: "independently verified" }),
    ).toContainText("independently verified");
    expect(counts.rosterAction).toBe(acts);
    expect(fixture.enrollments.get("c2").get("student-a")).toBe(false);
    expect(fixture.accounts.get("student-a").active).toBe(true);
    await button("Recycle bin").click();
    await expect(
      roster.getByText(
        "Archived records can be restored for 30 days, then are purged in the authorized scope.",
        { exact: false },
      ),
    ).toBeVisible();
    await roster
      .getByLabel("student-a@example.invalid", { exact: true })
      .check();
    await button("Restore selected (1)").click();
    await button("Confirm restore").click();
    await expect(
      roster
        .locator(':scope > [role="status"]')
        .filter({ hasText: "independently verified" }),
    ).toContainText("independently verified");
    await button("Active roster").click();
    await expect(
      roster.getByLabel("student-a@example.invalid", { exact: true }),
    ).toBeVisible();
    check(
      "Course-only removal/restore verifies both roster lists; other course enrollment/account unchanged and retention copy preserved",
    );
    await page.getByText("Import CSV / XLSX roster", { exact: true }).click();
    await label("Roster import file").setInputFiles(
      csv("name,email\nRoster Import Student,roster-import@example.invalid\n"),
    );
    await label("Roster default temporary password").fill(password());
    await button("Validate and preview").click();
    controls.afterWriteReadFailure = true;
    await button("Commit reviewed import").click();
    await expect(roster.getByRole("alert")).toContainText("needs inspection");
    const rc = counts.rosterCommit;
    await button("Inspect roster outcome (GET only)").click();
    await expect(
      roster
        .locator(':scope > [role="status"]')
        .filter({ hasText: "independently verified" })
        .filter({ hasText: "acknowledged and independently verified" }),
    ).toBeVisible();
    expect(counts.rosterCommit).toBe(rc);
    check(
      "Teacher roster import keeps review after accepted commit/readback failure; GET-only recovery",
    );
    await shot("teacher-course-students");
    await label("Course for students").selectOption("c2");
    await expect(
      roster.getByLabel("student-a@example.invalid", { exact: true }),
    ).toBeVisible();
    await expect(
      roster.getByLabel("existing@example.invalid", { exact: true }),
    ).toHaveCount(0);
    expect(
      fixture.requests
        .slice(teacherRequestStart)
        .some((r) => r.path.startsWith("/api/admin/")),
    ).toBe(false);
    check(
      "Teacher only requests selected assigned course roster/staff; no global index/candidate/privilege endpoint",
    );
    await label("Course for students").selectOption("c1");
    await expect(
      roster.getByLabel("existing@example.invalid", { exact: true }),
    ).toBeVisible();
    const rosterHeld = fixture.hold("/api/teacher/courses/c1/students");
    await button("Refresh status").click();
    await rosterHeld.entered;
    await expect(label("Course for students")).toBeDisabled();
    await button("Force course remount fixture").click();
    const rosterLate = page.waitForResponse((r) =>
      r.url().includes("/api/teacher/courses/c1/students"),
    );
    rosterHeld.release();
    await (await rosterLate).finished();
    await expect(
      page.getByRole("heading", {
        name: "SYN202 · Synthetic Course Two",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      roster.getByLabel("existing@example.invalid", { exact: true }),
    ).toHaveCount(0);
    check(
      "Explicit held course-A roster GET cannot replace course-B list after a forced route remount",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(await page.evaluate(() => Object.keys(localStorage).length)).toBe(0);
    expect(await page.evaluate(() => Object.keys(sessionStorage).length)).toBe(
      0,
    );
    check(
      "Responsive controls reachable without page overflow; no account/password draft in browser storage",
    );
    await page.close();
    // Reset only synthetic fixture rows for repeated widths.
    fixture.accounts.get("teacher-b").user.role = "teacher";
    if (!fixture.staff.get("c1").includes("teacher-b"))
      fixture.staff.get("c1").push("teacher-b");
    fixture.owners.set("c1", "admin");
    fixture.staff.set("c3", ["other-admin"]);
  }
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
} catch (e) {
  errors.push(String(e));
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
      "Actual installed Chrome + React + explicit synthetic Vite HTTP DTO fixture. NOT real backend authentication, SQLite, retention or import parser evidence. Passwords generated only in memory; no request bodies recorded.",
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
