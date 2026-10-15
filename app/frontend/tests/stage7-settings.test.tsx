import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { AiStatus, SearchSettings, Settings, User } from "../src/types";
import {
  connectionText,
  modelConnection,
  modelForm,
  modelPayload,
  modelReadbackMatches,
  permittedSection,
  searchForm,
  searchPayload,
  searchReadbackMatches,
} from "../src/stage7-settings";
import SettingsWorkspace from "../src/SettingsWorkspace";
import { api } from "../src/api";

const ai: AiStatus = {
  mode: "openai",
  configured: true,
  base_url: "http://fixture.invalid/v1",
  model: "Fixture model",
};
const settings: Settings = { ai, api_key_set: true };
const search: SearchSettings = {
  provider: "tavily",
  enabled: true,
  configured: true,
  api_key_set: true,
  api_key_source: "environment",
  connection: { status: "not_checked", checked_at: null, message: null },
};
const user: User = {
  id: "synthetic-admin",
  name: "Alex Fixture",
  email: "alex@example.invalid",
  role: "admin",
};
const noop = () => {};
describe("Stage7 settings", () => {
  it("a current runtime failure cannot inherit an old green connection check", () => {
    const current = modelConnection({...ai, last_error: "Current service failure", connection: {
      status: "connected", checked_at: "2026-10-07T18:00:00Z", message: "Earlier success"
    }});
    expect(current.status).toBe("error");
    expect(current.checked_at).toBeNull();
    expect(connectionText(current).label).toBe("Connection issue");
  });
  it("model saves only openai; blank keys are omitted and clear is explicit", () => {
    expect(modelPayload(modelForm(settings))).toEqual({
      mode: "openai",
      base_url: ai.base_url,
      model: ai.model,
    });
    expect(
      modelPayload({ ...modelForm(settings), api_key: "   " }),
    ).not.toHaveProperty("api_key");
    expect(
      modelPayload({ ...modelForm(settings), clear_key: true }),
    ).toHaveProperty("api_key", "");
  });
  it("search blank keeps, replacement and clear are mutually exclusive", () => {
    expect(searchPayload(searchForm(search))).toEqual({ enabled: true });
    expect(searchPayload({ ...searchForm(search), api_key: " " })).toEqual({
      enabled: true,
    });
    expect(
      searchPayload({
        ...searchForm(search),
        clear_key: true,
        api_key: "synthetic-placeholder",
      }),
    ).toEqual({ enabled: true, clear_api_key: true });
  });
  it("model readback detects divergent fields and wrong key state", () => {
    const f = modelForm(settings);
    expect(modelReadbackMatches(settings, f)).toBe(true);
    expect(
      modelReadbackMatches(settings, { ...f, base_url: `${f.base_url}/` }),
    ).toBe(true);
    expect(
      modelReadbackMatches({ ...settings, ai: { ...ai, model: "Other" } }, f),
    ).toBe(false);
    expect(modelReadbackMatches(settings, { ...f, clear_key: true })).toBe(
      false,
    );
    expect(
      modelReadbackMatches(
        { ...settings, api_key_set: false },
        { ...f, api_key: "synthetic-placeholder" },
      ),
    ).toBe(false);
  });
  it("search clear cannot silently revive environment keys", () => {
    const f = { ...searchForm(search), clear_key: true };
    expect(searchReadbackMatches(search, f)).toBe(false);
    expect(
      searchReadbackMatches(
        { ...search, api_key_set: false, api_key_source: "none" },
        f,
      ),
    ).toBe(true);
    expect(
      searchReadbackMatches(search, {
        ...f,
        clear_key: false,
        api_key: "synthetic-placeholder",
      }),
    ).toBe(false);
  });
  it("a configured URL or historical demo is never evidence of connectivity", () => {
    expect(modelConnection(ai).status).toBe("not_checked");
    expect(
      modelConnection({ ...ai, last_error: "Previous failure" }).status,
    ).toBe("error");
    expect(
      modelConnection({
        ...ai,
        mode: "demo",
        connection: { status: "connected", checked_at: null, message: null },
      }).status,
    ).toBe("not_configured");
  });
  it("dirty, checking and failed readback never show old success", () => {
    const check = {
      status: "connected" as const,
      checked_at: "2026-10-08T00:00:00Z",
      message: null,
    };
    expect(connectionText(check, true).label).toBe("Not checked");
    expect(connectionText(check, false, true).label).toBe("Checking…");
    expect(connectionText(check, false, false, true).label).toBe(
      "Status unavailable",
    );
    expect(connectionText(check).label).toBe("Last test succeeded");
    expect(connectionText(check).detail).toContain("Last checked:");
  });
  for (const role of ["teacher", "student"] as const) {
    for (const section of ["model", "search", "users"] as const) {
      it(`${role} direct ${section} mounts only the authorized personal/course scope`, () => {
        const privileged = vi.spyOn(api, "settings");
        const web = vi.spyOn(api, "searchSettings");
        const staff = vi.spyOn(api, "teachers");
        const u = { ...user, role };
        expect(permittedSection(u, section)).toBe(role === "teacher" && section === "users" ? "users" : "account");
        const html = renderToStaticMarkup(
          <SettingsWorkspace
            user={u}
            section={section}
            onSection={noop}
            onUserUpdate={noop}
            onAiUpdate={noop}
          />,
        );
        expect(html).toContain("Account");
        expect(html).not.toContain("AI Model");
        expect(html).not.toContain("Web Search");
        expect(html).not.toContain("Global User Accounts");
        if (role === "teacher") expect(html).toContain("Course Students");
        expect(privileged).not.toHaveBeenCalled();
        expect(web).not.toHaveBeenCalled();
        expect(staff).not.toHaveBeenCalled();
        vi.restoreAllMocks();
      });
    }
  }
  it("admins see the global sections and existing account form", () => {
    const html = renderToStaticMarkup(
      <SettingsWorkspace
        user={user}
        onSection={noop}
        onUserUpdate={noop}
        onAiUpdate={noop}
      />,
    );
    for (const label of [
      "Account",
      "AI Model",
      "Web Search",
      "Global User Accounts",
    ])
      expect(html).toContain(label);
    expect(html).toContain("Display name");
    expect(html).toContain("Change password");
  });
});
