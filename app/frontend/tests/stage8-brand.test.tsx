import {renderToStaticMarkup} from "react-dom/server";
import {describe,it,expect} from "vitest";
import {Brand} from "../src/ui";
import Login from "../src/Login";
const boot={app_name:"AIcademiya",demo_enabled:false,default_locale:"en" as const,ai:{mode:"openai" as const,configured:true,base_url:"",model:"Configured model"}};
describe("Stage8 brand and generic login",()=>{
 it("panel retains home-link semantics with light mark and visible brand text",()=>{const html=renderToStaticMarkup(<Brand appearance="panel"/>);expect(html).toContain('brand--panel');expect(html).toContain('aicademiya-mark-light.svg');expect(html).toContain('href="#/home"');expect(html).toContain('AIcademiya');expect(html).toContain('LEARN WITH INTENTION');});
 it("standard brand still supports non-inverted contexts",()=>{const html=renderToStaticMarkup(<Brand/>);expect(html).toContain('brand--standard');expect(html).toContain('aicademiya-mark.svg');});
 it("login is course-neutral and contains no anonymous model status",()=>{const html=renderToStaticMarkup(<Login bootstrap={boot} onAuthenticated={async()=>{}}/>);expect(html).not.toMatch(/EDUC7703|LANGUAGE ASSESSMENT|Active AI Model|Configured model|ai-badge/);expect(html).toContain('brand--standard');expect(html).toContain('LEARN WITH INTENTION');expect(html).toContain('type="password"');expect(html).toContain('autoComplete="current-password"');});
});
