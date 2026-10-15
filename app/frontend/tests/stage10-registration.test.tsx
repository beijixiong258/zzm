import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect, vi } from "vitest";
import Login from "../src/Login";
import { api } from "../src/api";
import { accessForm, accessReadbackMatches } from "../src/AccessSettings";
import SettingsWorkspace from "../src/SettingsWorkspace";
const boot = {app_name:"AIcademiya", demo_enabled:false, default_locale:"en" as const, ai:{mode:"openai" as const,configured:false,base_url:"",model:""}};
const login = (enabled: boolean) => renderToStaticMarkup(<Login bootstrap={{...boot,registration_enabled:enabled}} onAuthenticated={async()=>{}}/>);
describe("Stage10 registration controls",()=>{
 it("closed registration keeps light real sign-in and removes signup",()=>{const h=login(false);expect(h).toContain("currently closed");expect(h).not.toContain("Create student account");expect(h).toContain("brand--standard");expect(h).toContain('type="password"');expect(h).not.toContain('disabled=""');expect(h).not.toContain("Authentication is disabled");});
 it("open registration retains course-invite account entry",()=>{expect(login(true)).toContain("Create student account");expect(login(true)).not.toContain("currently closed");});
 it("unknown bootstrap doesn't advertise signup before policy loads",()=>{const h=renderToStaticMarkup(<Login bootstrap={null} onAuthenticated={async()=>{}}/>);expect(h).not.toContain("Create student account");expect(h).not.toContain("currently closed");});
 it("saved registration readback must exactly match submitted boolean",()=>{expect(accessForm({registration_enabled:false})).toEqual({registration_enabled:false});expect(accessReadbackMatches({registration_enabled:false},{registration_enabled:false})).toBe(true);expect(accessReadbackMatches({registration_enabled:true},{registration_enabled:false})).toBe(false);});
 it.each(["student","teacher"] as const)("%s cannot reach admin access controls",role=>{const h=renderToStaticMarkup(<SettingsWorkspace user={{id:role,role,name:"Synthetic",email:"synthetic@example.invalid"}} section="users" onSection={()=>{}} onUserUpdate={()=>{}} onAiUpdate={()=>{}}/>);expect(h).not.toContain("New student registration");expect(h).not.toContain("User Management");});
 it("writes the explicit boolean through admin PUT, never client-local policy",async()=>{const f=vi.fn().mockResolvedValue(new Response(JSON.stringify({registration_enabled:false}),{status:200}));vi.stubGlobal("fetch",f);try{await api.saveAccessSettings({registration_enabled:false});expect(f.mock.calls[0][0]).toBe("/api/admin/access-settings");expect(f.mock.calls[0][1].method).toBe("PUT");expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({registration_enabled:false});expect(f.mock.calls[0][1].credentials).toBe("include");}finally{vi.unstubAllGlobals();}});
});
