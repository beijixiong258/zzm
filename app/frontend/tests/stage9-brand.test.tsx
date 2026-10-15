import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import Login from "../src/Login";
import { Brand } from "../src/ui";

const root = path.resolve(import.meta.dirname, "../..");
const baseline = path.join(root, "artifacts/stage9/branding/baseline");
const read = (file: string) => fs.readFileSync(path.join(root, "frontend/src", file), "utf8");
const boot = {app_name:"AIcademiya",demo_enabled:false,default_locale:"en" as const,ai:{mode:"openai" as const,configured:true,base_url:"",model:"not contacted"}};
const html = (previewAppearance?: "standard" | "panel", ready = true) => renderToStaticMarkup(<Login bootstrap={ready ? boot : null} onAuthenticated={async () => { throw new Error("Not an auth test"); }} previewAppearance={previewAppearance}/>);

describe("Stage9 V4 brand / safe Login preview", () => {
  it("production uses the selected light palette with enabled authentication", () => {
    const markup = html();
    expect(markup).toContain("brand--standard");
    expect(markup).toContain("/aicademiya-mark.svg");
    expect(markup).not.toContain("data-brand-preview");
    expect(markup).not.toContain("Authentication is disabled");
    expect(markup).not.toContain("disabled=\"\"");
    expect(markup).toContain('autoComplete="current-password"');
    expect(markup).not.toMatch(/EDUC7703|ai-badge|not contacted/);
  });
  for (const appearance of ["standard", "panel"] as const) {
    it(`${appearance} preview disables every input and both buttons`, () => {
      const markup = html(appearance);
      expect(markup).toContain(`data-brand-preview="${appearance}"`);
      expect(markup).toContain(`brand--${appearance}`);
      expect(markup).toContain(appearance === "standard" ? "/aicademiya-mark.svg" : "/aicademiya-mark-light.svg");
      expect(markup.match(/disabled=""/g)).toHaveLength(4);
      expect(markup).toContain("Visual preview only. Authentication is disabled.");
    });
  }
  it("bootstrap still gates the live sign-in button", () => {
    expect(html(undefined, false).match(/disabled=""/g)).toHaveLength(1);
  });
  it("auth submit core and form rules retain exact Stage8 code", () => {
    const before = fs.readFileSync(path.join(baseline, "Login.tsx"), "utf8");
    const after = read("Login.tsx");
    const submit = (s: string) => s.slice(s.indexOf("  async function submit"), s.indexOf("  return ("));
    expect(submit(after).replace("    if (preview) return;\n", "")).toBe(submit(before));
    let normalized = after
      .replace("  previewAppearance,\n", "")
      .replace("  const registrationOpen = bootstrap !== null && bootstrap.registration_enabled !== false;\n", "")
      .replace("  const [wantsRegister, setRegister] = useState(false);\n  const register = wantsRegister && registrationOpen;", "  const [register, setRegister] = useState(false);")
      .replace('{registrationOpen ? <p className="switch-auth">', '<p className="switch-auth">')
      .replace('</p> : bootstrap && <p className="switch-auth" role="status">New student registration is currently closed. Existing accounts can still sign in.</p>}', '</p>')
      .replace('  /** Explicit visual preview only; any value disables authentication controls. */\n  previewAppearance?: "standard" | "panel";\n', "")
      .replace("  const preview = previewAppearance !== undefined;\n", "")
      .replace("    if (preview) return;\n", "")
      .replace(" data-brand-preview={previewAppearance}", "")
      .replace('appearance={previewAppearance ?? "standard"}', 'appearance="panel"')
      .replace('        {preview && <p className="login-preview-notice" role="note">Visual preview only. Authentication is disabled.</p>}\n', "")
      .replace(/^\s+disabled={preview}\n/gm, "")
      .replace("disabled={preview || !!busy || !bootstrap}", "disabled={!!busy || !bootstrap}");
    expect(normalized).toBe(before);
  });
  it("Brand navigation and unchanged UI exports retain the branding baseline", () => {
    // Stage16 intentionally replaces AiBadge's historical check with live health.
    // Keep the branding/common-export byte guard, not the obsolete whole-file freeze.
    const unchanged = (s: string) => s.slice(s.indexOf("export function Brand"), s.indexOf("export function AiBadge")) + s.slice(s.indexOf("export function Empty"));
    expect(unchanged(read("ui.tsx"))).toBe(unchanged(fs.readFileSync(path.join(baseline, "ui.tsx"), "utf8")));
    expect(renderToStaticMarkup(<Brand/>)).toContain('href="#/home"');
  });
  it("styles.css changes only the 13 paired sidebar dimension values", () => {
    let expected = fs.readFileSync(path.join(baseline, "styles.css"), "utf8");
    for (const [from, to] of [[224,288],[242,288],[196,264],[182,264]]) {
      expected = expected.replaceAll(`width: ${from}px;`, `width: ${to}px;`)
        .replaceAll(`margin-left: ${from}px;`, `margin-left: ${to}px;`)
        .replaceAll(`width: calc(100% - ${from}px);`, `width: calc(100% - ${to}px);`);
    }
    expect(read("styles.css")).toBe(expected);
  });
  it("all 8 V4 public assets remain byte-identical to pre-edit baseline", () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(root,"artifacts/stage9/branding/baseline-manifest.json"),"utf8"));
    expect(Object.keys(manifest.publicAssets)).toHaveLength(8);
    for (const [file, hash] of Object.entries(manifest.publicAssets)) {
      expect(crypto.createHash("sha256").update(fs.readFileSync(path.join(root,"frontend/public",file))).digest("hex")).toBe(hash);
    }
  });
});
